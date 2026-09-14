using System.Collections.Generic;
using Maps;
using Maps.MapAssembler;
using Maps.MapGenerator;
using Others;
using UnityEngine;

namespace Managers.Map
{
    /// <summary>
    ///     MapManager is an abstract class used to implement any kind of map manager. A map manager manages
    ///     the creation process of a map, which consists in generation (performed by a map generator),
    ///     assembling (performed by a map assembler) and population (performed by an object displacer).
    /// </summary>
    public abstract class MapManager : CoreComponent
    {
        [Header("Core components")] [SerializeField]
        protected MapGenerator mapGeneratorScript;

        [SerializeField] protected MapAssembler mapAssemblerScript;

        [SerializeField] protected ObjectDisplacer objectDisplacerScript;

        [Header("Import")]
        // Do I have to load the map from a .txt?
        [SerializeField]
        protected bool loadMapFromFile;

        // Path of the map to be laoded.
        [SerializeField] protected string textFilePath;

        [Header("Other")]
        // Category of the spawn point gameobjects in the object displacer. 
        [SerializeField]
        protected string spawnPointCategory;

        protected bool export;
        protected string exportPath;
        protected bool flip;

        protected string seed;

        public float MapScale => mapAssemblerScript.GetMapScale();

        private void Start()
        {
            ExtractParametersFromManager();
        }

        private void Update()
        {
            var generatorReady = mapGeneratorScript == null || mapGeneratorScript.IsReady();
            if (!IsReady() && mapAssemblerScript.IsReady() && generatorReady &&
                objectDisplacerScript.IsReady())
                SetReady(true);
        }

        public void SetTextFile(string mapPath)
        {
            loadMapFromFile = true;
            textFilePath = mapPath;
        }

        public abstract void ManageMap(bool assembleMap);

        // Returns the spawn points.k
        public List<GameObject> GetSpawnPoints()
        {
            return objectDisplacerScript.GetObjectsByCategory(spawnPointCategory);
        }

        // Loads the map from a text file.
        protected abstract void LoadMapFromText();

        // Extracts the parameters from the parameter Manager, if any.
        protected void ExtractParametersFromManager()
        {
            if (ParameterManager.HasInstance())
            {
                export = ParameterManager.Instance.Export;
                exportPath = ParameterManager.Instance.ExportPath;
                flip = ParameterManager.Instance.Flip;

                switch (ParameterManager.Instance.GenerationMode)
                {
                    case 0:
                        loadMapFromFile = false;
                        seed = ParameterManager.Instance.MapDNA;
                        break;
                    case 1:
                        loadMapFromFile = false;
                        seed = ParameterManager.Instance.MapDNA;
                        break;
                    case 2:
                        loadMapFromFile = true;
                        seed = null;
                        textFilePath = ParameterManager.Instance.MapDNA;
                        break;
                    case 3:
                        loadMapFromFile = false;
                        seed = ParameterManager.Instance.MapDNA;
                        textFilePath = ParameterManager.Instance.MapDNA;
                        break;
                    case 4:
                        loadMapFromFile = true;
                        seed = ParameterManager.Instance.MapDNA;
                        textFilePath = null;
                        break;
                }
            }
        }

        // Returns the Map Generator.
        public MapGenerator GetMapGenerator()
        {
            return mapGeneratorScript;
        }

        // Returns the Map Assembler.
        public MapAssembler GetMapAssembler()
        {
            return mapAssemblerScript;
        }

        // Resets the map.
        public void ResetMap()
        {
            if (mapGeneratorScript != null) mapGeneratorScript.ResetMapSize();
            mapAssemblerScript.ClearMap();
            objectDisplacerScript.DestroyAllCustomObjects();
            SetReady(false);
        }

        public bool GetFlip()
        {
            return flip;
        }

        public abstract char[,] GetMap();
        public abstract Area[] GetAreas();
    }
}