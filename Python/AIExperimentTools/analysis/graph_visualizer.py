"""Four diagnostic graph views adapted from Ballabio & Loiacono (2019, IV-C).

Original All-Black room primitives are not available for every generator. Derive
disjoint rectangles from the final grid instead; these are regions, not recovered
design rooms. These display graphs do not change topology metrics or simulation.
"""
import json
import math
import warnings
from pathlib import Path

import networkx as nx
import numpy as np

from analysis.run_analysis import RunAnalysis
from map_schema.canonical_map import WALKABLE_SYMBOLS


def rectangle_regions(map_data):
    """Merge identical horizontal floor runs in successive rows into rectangles."""
    rectangles, active = [], {}
    for y, row in enumerate(map_data.grid):
        spans, x = [], 0
        while x < map_data.width:
            if row[x] not in WALKABLE_SYMBOLS:
                x += 1
                continue
            left = x
            while x < map_data.width and row[x] in WALKABLE_SYMBOLS:
                x += 1
            spans.append((left, x))
        current = {}
        for left, right in spans:
            index = active.get((left, right))
            if index is None:
                index = len(rectangles)
                rectangles.append([left, y, right, y + 1])
            else:
                rectangles[index][3] = y + 1
            current[left, right] = index
        active = current
    return [tuple(rectangle) for rectangle in rectangles]


def build_graph_views(map_data):
    """Build outlines, eight-neighbour tiles, derived regions, and object nodes."""
    outlines, tiles, rooms = nx.Graph(), nx.Graph(), nx.Graph()
    walkable = set(map_data.walkable_cells())
    for x, y in sorted(walkable):
        tiles.add_node((x, y), pos=(x, y), type="tile")
    # Positive half-neighbourhood avoids adding each undirected edge twice.
    # Diagonal corner contact follows the paper's eight-neighbour definition;
    # it is not a claim about Unity movement clearance.
    for x, y in sorted(walkable):
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            neighbor = x + dx, y + dy
            if neighbor in walkable:
                tiles.add_edge((x, y), neighbor, weight=math.hypot(dx, dy))

    owners = {}
    for index, (left, top, right, bottom) in enumerate(rectangle_regions(map_data)):
        rooms.add_node(index, pos=((left + right - 1) / 2, (top + bottom - 1) / 2),
                       type="room", bounds=(left, top, right, bottom))
        corners = [(left - .5, top - .5), (right - .5, top - .5),
                   (right - .5, bottom - .5), (left - .5, bottom - .5)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            outlines.add_node(a, pos=a, type="corner")
            outlines.add_node(b, pos=b, type="corner")
            outlines.add_edge(a, b, weight=math.dist(a, b))
        for y in range(top, bottom):
            for x in range(left, right):
                owners[x, y] = index
    # Disjoint derived regions share traversable boundaries rather than overlap.
    for (x, y), owner in owners.items():
        for neighbor in ((x + 1, y), (x, y + 1)):
            other = owners.get(neighbor)
            if other is not None and other != owner:
                rooms.add_edge(owner, other,
                               weight=math.dist(rooms.nodes[owner]["pos"],
                                                rooms.nodes[other]["pos"]))
    elements = rooms.copy()
    for x, y, symbol in map_data.iter_cells():
        if symbol in {"S", "H", "A"}:
            node = "element", x, y
            elements.add_node(node, pos=(x, y), type=symbol)
            owner = owners[x, y]
            elements.add_edge(node, owner,
                              weight=math.dist((x, y), rooms.nodes[owner]["pos"]))
    return {"outlines": outlines, "tiles": tiles, "rooms": rooms,
            "rooms_and_elements": elements}


def draw_graph_views(plt, map_data, path, dpi=160, title=None):
    """Write a bounded-size four-panel image; all panels use canonical coordinates."""
    from matplotlib.collections import LineCollection
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D

    views = build_graph_views(map_data)
    figure, axes = plt.subplots(2, 2, figsize=(10, 10))
    floor = np.array([[cell in WALKABLE_SYMBOLS for cell in row] for row in map_data.grid])
    titles = ["Derived region outlines", "Tiles graph (8 neighbours)",
              "Derived rooms / regions graph", "Derived regions and game elements"]
    styles = {"S": ("#2563EB", "s", "Spawn"),
              "H": ("#16A34A", "^", "Health"),
              "A": ("#D97706", "D", "Ammo")}
    for ax, (name, graph), label in zip(axes.flat, views.items(), titles):
        ax.imshow(floor, cmap=ListedColormap(["white", "#F1F5F9"]),
                  vmin=0, vmax=1, origin="upper", interpolation="nearest")
        positions = nx.get_node_attributes(graph, "pos")
        ax.add_collection(LineCollection([(positions[a], positions[b]) for a, b in graph.edges],
                                        colors="#64748B", linewidths=.45, alpha=.8))
        base = [pos for node, pos in positions.items()
                if graph.nodes[node]["type"] not in styles]
        if base:
            ax.scatter(*zip(*base), s=3 if name == "tiles" else 13,
                       c="#DC2626", zorder=3, linewidths=0)
        for symbol, (color, marker, _) in styles.items():
            points = [pos for node, pos in positions.items() if graph.nodes[node]["type"] == symbol]
            if points:
                ax.scatter(*zip(*points), s=32, c=color, marker=marker,
                           edgecolors="white", linewidths=.4, zorder=4)
        ax.set(xlim=(-.75, map_data.width - .25), ylim=(map_data.height - .25, -.75),
               aspect="equal", xticks=[], yticks=[])
        ax.set_title(f"{label}\n{len(graph)} nodes, {graph.number_of_edges()} edges", fontsize=10)
        if not positions:
            ax.text(.5, .5, "No walkable cells", transform=ax.transAxes, ha="center")
        for spine in ax.spines.values():
            spine.set_visible(False)
    figure.legend(handles=[Line2D([], [], linestyle="none", marker=marker,
                                  color=color, label=label)
                           for color, marker, label in styles.values()],
                  loc="lower center", bbox_to_anchor=(.5, .055), ncol=3, frameon=False)
    figure.suptitle(title or map_data.map_id, fontsize=12, wrap=True)
    figure.text(.5, .015, "Regions: row-run rectangle decomposition, not original generator rooms.\n"
                "Region links: shared floor boundary. Tile diagonals include corner contacts; not Unity paths.",
                ha="center", fontsize=8)
    figure.tight_layout(rect=(0, .10, 1, .94))
    try:
        figure.savefig(path, dpi=dpi, facecolor="white")
    finally:
        plt.close(figure)
    return path


def create_graph_visualizations(plt, groups, output, dpi=160):
    """One four-panel PNG per unique final map within each experiment config."""
    output.mkdir(parents=True, exist_ok=True)
    images = []
    for group in groups:
        seen = set()
        for run in group["runs"]:
            folder = Path(run["folder"])
            config_path = folder / "experiment_evaluated.json"
            if not config_path.exists():
                config_path = folder / "experiment.json"
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            for context in RunAnalysis(folder, config).load_final():
                map_data = context.canonical_map
                if map_data is None:
                    warnings.warn(f"Graph views skipped: map unavailable in {folder.name}")
                    continue
                key = map_data.content_hash()
                if key in seen:
                    continue
                seen.add(key)
                path = output / f"graphs_{group['plot_name']}_{len(seen):04d}.png"
                images.append(draw_graph_views(plt, map_data, path, dpi,
                              title=f"{group['name']} | {folder.name}\n{map_data.map_id}"))
    return images
