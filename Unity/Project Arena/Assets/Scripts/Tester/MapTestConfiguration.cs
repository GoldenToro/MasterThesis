using System;
using AI;
using Newtonsoft.Json;

namespace Tester
{
    [Serializable]
    public class MapTestConfiguration
    {
        [JsonProperty("schema_version")] public string schemaVersion = "1.0";
        [JsonProperty("experiment_name")] public string experimentName = "experiment";
        [JsonProperty("num_experiments")] public int numExperiments = 1;
        [JsonProperty("game_length")] public int gameLength = 240;
        [JsonProperty("ready_duration")] public int readyDuration = 1;
        [JsonProperty("score_duration")] public int scoreDuration;
        [JsonProperty("respawn_duration")] public float respawnDuration = 3.0f;
        [JsonProperty("paths")] public MapTestPaths paths = new MapTestPaths();
        [JsonProperty("logging")] public MapTestLogging logging = new MapTestLogging();
        [JsonProperty("map")] public CanonicalGridConfiguration map = new CanonicalGridConfiguration();
        [JsonProperty("bot1")] public MapTestBotConfiguration bot1 = MapTestBotConfiguration.CreateDefault(1);
        [JsonProperty("bot2")] public MapTestBotConfiguration bot2 = MapTestBotConfiguration.CreateDefault(2);
    }

    [Serializable]
    public class MapTestPaths
    {
        [JsonProperty("bots_directory")] public string botsDirectory = "Bots";
        [JsonProperty("output_directory")] public string outputDirectory = "Export";
        [JsonProperty("output_subdirectory")] public string outputSubdirectory = "";
    }

    [Serializable]
    public class MapTestLogging
    {
        [JsonProperty("save_map")] public bool saveMap = true;
        [JsonProperty("log_positions")] public bool logPositions = true;
        [JsonProperty("log_kill_distances")] public bool logKillDistances;
        [JsonProperty("log_death_positions")] public bool logDeathPositions = true;
    }

    [Serializable]
    public class CanonicalGridConfiguration
    {
        [JsonProperty("map_id")] public string mapId = "map";
        [JsonProperty("width")] public int width;
        [JsonProperty("height")] public int height;
        [JsonProperty("map_scale")] public float mapScale = 1.0f;
        [JsonProperty("grid")] public string[] grid = Array.Empty<string>();
        [JsonProperty("symbols")] public MapSymbolConfiguration symbols = new MapSymbolConfiguration();
    }

    [Serializable]
    public class MapSymbolConfiguration
    {
        [JsonProperty("wall")] public string wall = "#";
        [JsonProperty("floor")] public string floor = ".";
        [JsonProperty("spawn")] public string spawn = "S";
        [JsonProperty("health")] public string health = "H";
        [JsonProperty("ammo")] public string ammo = "A";
    }

    [Serializable]
    public class MapTestBotConfiguration
    {
        [JsonProperty("id")] public int id;
        [JsonProperty("file")] public string file;
        [JsonProperty("skill")] public float skill = 0.5f;
        [JsonProperty("params_file")] public string paramsFile;
        [JsonProperty("guns_file")] public string gunsFile;
        [JsonProperty("parameters")] public JSonBotCharacteristics parameters;
        [JsonProperty("guns")] public bool[] guns;

        public static MapTestBotConfiguration CreateDefault(int identifier)
        {
            return new MapTestBotConfiguration
            {
                id = identifier,
                file = "assault",
                skill = 0.5f
            };
        }
    }
}
