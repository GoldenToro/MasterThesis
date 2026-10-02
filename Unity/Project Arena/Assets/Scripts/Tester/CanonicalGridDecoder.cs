using System;
using System.Text;

namespace Tester
{
    public sealed class DecodedCanonicalMap
    {
        public char[,] Grid { get; }
        public string NormalizedText { get; }
        public int SpawnCount { get; }

        public DecodedCanonicalMap(char[,] grid, string normalizedText, int spawnCount)
        {
            Grid = grid;
            NormalizedText = normalizedText;
            SpawnCount = spawnCount;
        }
    }

    /// <summary>
    /// Converts the thesis canonical symbols to the internal Project Arena symbols.
    /// Internal symbols: w wall, r floor, s spawn, d cover/decoration, h health, a ammo.
    /// </summary>
    public static class CanonicalGridDecoder
    {
        public static DecodedCanonicalMap Decode(CanonicalGridConfiguration map)
        {
            if (map == null)
                throw new ArgumentNullException(nameof(map));
            if (map.grid == null || map.grid.Length == 0)
                throw new ArgumentException("The JSON map contains no grid rows.");

            var height = map.grid.Length;
            var width = map.grid[0] == null ? 0 : map.grid[0].Length;
            if (width == 0)
                throw new ArgumentException("The JSON map contains an empty first row.");

            if (map.height > 0 && map.height != height)
                throw new ArgumentException($"Map height is {map.height}, while the grid contains {height} rows.");
            if (map.width > 0 && map.width != width)
                throw new ArgumentException($"Map width is {map.width}, while the grid contains {width} columns.");

            var symbols = map.symbols ?? new MapSymbolConfiguration();
            var wall = ReadSymbol(symbols.wall, '#', "wall");
            var floor = ReadSymbol(symbols.floor, '.', "floor");
            var spawn = ReadSymbol(symbols.spawn, 'S', "spawn");
            var health = ReadSymbol(symbols.health, 'H', "health");
            var ammo = ReadSymbol(symbols.ammo, 'A', "ammo");

            var result = new char[height, width];
            var text = new StringBuilder();
            var spawnCount = 0;

            for (var row = 0; row < height; row++)
            {
                var line = map.grid[row];
                if (line == null || line.Length != width)
                    throw new ArgumentException($"Grid row {row} has a different width.");

                for (var column = 0; column < width; column++)
                {
                    var source = line[column];
                    var target = ConvertSymbol(source, wall, floor, spawn, health, ammo);
                    result[row, column] = target;
                    text.Append(target);
                    if (target == 's') spawnCount++;
                }

                if (row < height - 1) text.AppendLine();
            }

            if (spawnCount < 2)
                throw new ArgumentException($"The map needs at least two spawn tiles. Found {spawnCount}.");

            return new DecodedCanonicalMap(result, text.ToString(), spawnCount);
        }

        private static char ConvertSymbol(
            char source,
            char wall,
            char floor,
            char spawn,
            char health,
            char ammo)
        {
            if (source == wall || source == 'w') return 'w';
            if (source == floor || source == 'r') return 'r';
            if (source == spawn || source == 's') return 's';
            if (source == health || source == 'h') return 'h';
            if (source == ammo || source == 'a') return 'a';

            throw new ArgumentException($"Unsupported map symbol '{source}'.");
        }

        private static char ReadSymbol(string value, char fallback, string name)
        {
            if (string.IsNullOrEmpty(value)) return fallback;
            if (value.Length != 1)
                throw new ArgumentException($"The {name} symbol must contain exactly one character.");
            return value[0];
        }
    }
}
