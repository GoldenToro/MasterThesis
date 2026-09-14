using System;
using Maps;
using Maps.MapGenerator;

namespace Managers.Map
{
    /// <summary>
    /// Map manager for maps that already exist as a character grid.
    /// It skips procedural generation and directly assembles the provided grid.
    /// </summary>
    public class GridMapManager : MapManager
    {
        private char[,] map;

        [UnityEngine.SerializeField] private char wallChar = 'w';
        [UnityEngine.SerializeField] private char roomChar = 'r';

        public void SetMap(char[,] sourceMap, float mapScale)
        {
            if (sourceMap == null)
                throw new ArgumentNullException(nameof(sourceMap));
            if (sourceMap.GetLength(0) < 2 || sourceMap.GetLength(1) < 2)
                throw new ArgumentException("The map grid must contain at least two rows and two columns.");

            map = (char[,]) sourceMap.Clone();
            mapAssemblerScript.SetMapScale(mapScale);
            SetReady(false);
        }

        public override void ManageMap(bool assembleMap)
        {
            if (map == null)
                throw new InvalidOperationException("No grid has been assigned to GridMapManager.");

            if (assembleMap)
            {
                mapAssemblerScript.AssembleMap(map, wallChar, roomChar);
                objectDisplacerScript.DisplaceObjects(map, mapAssemblerScript.GetMapScale(), 0);
            }
        }

        protected override void LoadMapFromText()
        {
            throw new InvalidOperationException("GridMapManager receives its map through SetMap().");
        }

        public override char[,] GetMap()
        {
            if (map == null)
                throw new InvalidOperationException("No grid has been assigned to GridMapManager.");
            return (char[,]) map.Clone();
        }

        public override Area[] GetAreas()
        {
            return Array.Empty<Area>();
        }
    }
}
