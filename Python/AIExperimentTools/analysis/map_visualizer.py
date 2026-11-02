"""Final maps, movement, deaths, and grid visibility: one PNG per experiment config."""
import json
from pathlib import Path

import numpy as np

from analysis.run_analysis import RunAnalysis
from generators.registry import generator_color
from metrics.metric_calculator import _visibility_bundle, _world_to_cell


def position_heatmap(context, deaths=False):
    """Count both bots' logged positions per tile; None means logs are missing."""
    prefix = "death_positions" if deaths else "position"
    if not any(context.raw_files(f"{prefix}_*_bot{bot}.csv") for bot in (1, 2)):
        return None
    map_data = context.canonical_map
    counts = np.zeros((map_data.height, map_data.width))
    positions = context.death_positions if deaths else context.positions
    for bot in (1, 2):
        for position in positions(bot):
            cell = _world_to_cell(context, position)
            if cell is not None:
                x, y = cell
                counts[y, x] += 1
    return counts


def map_layers(context, columns=(0, 1, 2, 3)):
    map_data = context.canonical_map
    if map_data is None:
        return None
    symbols = {"#": 0, ".": 1, "S": 2, "H": 3, "A": 4}
    layout = np.array([[symbols[cell] for cell in row] for row in map_data.grid])
    visibility = None
    if 3 in columns:
        visibility = np.zeros(layout.shape)
        for (x, y), score in _visibility_bundle(context)["scores"].items():
            visibility[y, x] = score
    return (layout, position_heatmap(context) if 1 in columns else None,
            position_heatmap(context, deaths=True) if 2 in columns else None, visibility)


def draw_generator(plt, generator, maps, output, dpi, movement_log_scale=True,
                   *, death_log_scale=True, name=None, plot_name=None, color=None,
                   columns=(0, 1, 2, 3), deduplicate=True, title=None, horizontal=False,
                   hide_objects=False):
    from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm, Normalize
    from matplotlib.lines import Line2D

    # Keep the first occurrence and its simulation logs for each complete map.
    total_maps = len(maps)
    unique_maps, seen = [], set()
    for entry in maps:
        map_data = entry[1].canonical_map
        if deduplicate and map_data is not None:
            key = map_data.content_hash()
            if key in seen:
                continue
            seen.add(key)
        unique_maps.append(entry)
    maps = unique_maps
    layers = [map_layers(context, columns) for _, context in maps]
    if horizontal:
        figure = plt.figure(figsize=(3.25 * len(maps) + 1.7, 3.45 * len(columns) + 1.5))
        grid = figure.add_gridspec(
            2 * len(columns) + 1, len(maps) + 1,
            height_ratios=[0.6] + [0.3, 2.8] * len(columns),
            width_ratios=[1] * len(maps) + [0.45],
            left=0.025, right=0.975, top=1 - 0.65 / figure.get_figheight(),
            bottom=0.3 / figure.get_figheight(), hspace=0.15, wspace=0.18,
        )
        axes = [{column: figure.add_subplot(grid[2 * index + 2, row])
                 for index, column in enumerate(columns)} for row in range(len(maps))]
        legend_axes = {column: figure.add_subplot(grid[2 * index + 2, -1])
                       for index, column in enumerate(columns)}
    else:
        figure = plt.figure(figsize=(max(4.5, 3.25 * len(columns)), 3.6 * len(maps) + 1.2))
        grid = figure.add_gridspec(
            2 * len(maps) + 1, len(columns), height_ratios=[0.3, 2.8] * len(maps) + [0.7],
            left=0.025, right=0.975, top=1 - 0.7 / figure.get_figheight(),
            bottom=0.35 / figure.get_figheight(), hspace=0.18, wspace=0.18,
        )
        axes = [{column: figure.add_subplot(grid[2 * row + 1, index])
                 for index, column in enumerate(columns)} for row in range(len(maps))]
        legend_axes = {column: figure.add_subplot(grid[-1, index])
                       for index, column in enumerate(columns)}
    for ax in legend_axes.values():
        ax.set_axis_off()
    layout_colors = ListedColormap(["#263238", "white", "#3B82F6", "#22C55E", "#F59E0B"])
    background_colors = ListedColormap(["#263238", "#F1F5F9"])
    movement_background = ListedColormap(["#263238", "black"])
    column_labels = ["Map", "Movement samples / tile", "Deaths / tile", "Visibility fraction (8 directions)"]
    if movement_log_scale:
        column_labels[1] += " (log scale)"
    if death_log_scale:
        column_labels[2] += " (log scale)"
    if horizontal:
        for index, column in enumerate(columns):
            heading = figure.add_subplot(grid[2 * index + 1, :-1])
            heading.set_axis_off()
            heading.text(0.5, 0.5, column_labels[column], ha="center", va="center", fontsize=10)
    maxima = [max((float(layer[column].max()) for layer in layers
                   if layer is not None and layer[column] is not None), default=0)
              for column in range(1, 4)]
    death_max = int(maxima[1])
    death_colors = plt.get_cmap("Reds", death_max + 1)
    death_norm = (LogNorm(vmin=1, vmax=max(2, death_max)) if death_log_scale
                  else BoundaryNorm(np.arange(death_max + 2) - 0.5, death_colors.N))
    heat_images = {}
    for row, ((run_name, context), layer) in enumerate(zip(maps, layers)):
        heading = figure.add_subplot(grid[0, row] if horizontal else grid[2 * row, :])
        heading.set_axis_off()
        label = (run_name + ("\n" if horizontal else " | ")) if run_name else ""
        heading.text(0.5, 0.5, label + context.record['map_id'],
                     ha="center", va="center", fontsize=8 if horizontal else 10)
        for column in columns:
            ax = axes[row][column]
            ax.set_xticks([])
            ax.set_yticks([])
            if not horizontal:
                ax.set_title(column_labels[column], fontsize=9)
            if layer is None:
                ax.text(0.5, 0.5, "Map unavailable", transform=ax.transAxes, ha="center")
                continue
            layout = layer[0]
            if column == 0:
                ax.imshow(np.minimum(layout, 1) if hide_objects else layout,
                          cmap=layout_colors, vmin=0, vmax=4, origin="upper", interpolation="nearest")
                continue
            ax.imshow(layout != 0, cmap=movement_background if column == 1 else background_colors, vmin=0, vmax=1,
                      origin="upper", interpolation="nearest")
            values = layer[column]
            if values is None:
                ax.text(0.5, 0.5, "Logs unavailable", transform=ax.transAxes,
                        ha="center", bbox={"facecolor": "white", "alpha": 0.85})
                continue
            logarithmic = ((column == 1 and movement_log_scale)
                           or (column == 2 and death_log_scale))
            mask = (layout == 0) | ((values <= 0) if logarithmic or column == 1 else False)
            norm = (LogNorm(vmin=1, vmax=max(2, maxima[column - 1])) if logarithmic
                    else Normalize(vmin=0, vmax=maxima[column - 1] or 1))
            if column == 2:
                norm = death_norm
            heat_images[column] = ax.imshow(np.ma.masked_where(mask, values),
                                        cmap=("magma", death_colors, "viridis")[column - 1],
                                        norm=norm,
                                        origin="upper", interpolation="nearest")
            if column in (1, 2) and not values.any():
                ax.text(0.5, 0.5, "No recorded deaths" if column == 2 else "No recorded movement",
                        transform=ax.transAxes, ha="center", fontsize=8,
                        bbox={"facecolor": "white", "alpha": 0.85})
    for column, image in heat_images.items():
        options = {}
        if column == 2:
            step = max(1, int(np.ceil(death_max / 6)))
            ticks = list(range(0, death_max + 1, step))
            ticks[-1] = death_max  # Keep the endpoint without crowding the preceding tick.
            options = {"ticks": ticks,
                       "format": "%d", "drawedges": True}
            if death_log_scale:
                options["ticks"] = np.unique(np.geomspace(1, max(1, death_max), 7).round()).astype(int)
                options["boundaries"] = np.arange(1, max(1, death_max) + 2) - 0.5
        colorbar = figure.colorbar(
            image, cax=legend_axes[column].inset_axes(
                [0.15, 0.08, 0.15, 0.84] if horizontal else [0.08, 0.4, 0.84, 0.18]),
            orientation="vertical" if horizontal else "horizontal", **options,
        )
        if horizontal:
            colorbar.ax.tick_params(labelsize=8)
        else:
            colorbar.ax.set_title(column_labels[column], fontsize=8, pad=6)
    handles = [Line2D([], [], linestyle="none", marker="s", markersize=7,
                      markerfacecolor=shade, markeredgecolor="black", label=label)
               for label, shade in zip(("Walls", "Floor", "Spawns", "Health", "Ammo"),
                                       layout_colors.colors)]
    if hide_objects:
        handles = handles[:2]
    legend_axes[0].legend(handles=handles, title="Map", loc="center" if horizontal else "upper center",
                          ncol=1 if horizontal else 2, frameon=False, fontsize=8, title_fontsize=8)
    figure.suptitle(title if title is not None else f"{name or generator} — final maps",
                   color=color or generator_color(generator), fontsize=12,
                   y=1 - 0.12 / figure.get_figheight())
    if total_maps > len(maps):
        figure.text(
            0.5, 0.12 / figure.get_figheight(),
            f"Duplicates omitted: {total_maps - len(maps)} of {total_maps} final maps "
            "(identical layout and object positions).",
            fontsize=9, ha="center", va="bottom",
        )
    path = output / f"maps_{plot_name or generator}.png"
    figure.savefig(path, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    return path


def create_map_visualizations(plt, groups, output, dpi=160, movement_log_scale=True, death_log_scale=True):
    """Reuse comparison groups so only repeats of the same config share an image."""
    output.mkdir(parents=True, exist_ok=True)
    images = []
    for group in groups:
        maps = []
        for run in group["runs"]:
            folder = Path(run["folder"])
            config_path = folder / "experiment_evaluated.json"
            if not config_path.exists():
                config_path = folder / "experiment.json"
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            analysis = RunAnalysis(folder, config)
            maps.extend((folder.name, context) for context in analysis.load_final())
        if maps:
            images.append(draw_generator(
                plt, group["generator"], maps, output, dpi, movement_log_scale,
                death_log_scale=death_log_scale,
                name=group["name"], plot_name=group["plot_name"], color=group["color"],
            ))
    return images
