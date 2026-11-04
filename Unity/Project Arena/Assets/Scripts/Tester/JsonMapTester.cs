using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using AI;
using Logging;
using Managers;
using Managers.Map;
using Managers.Mode;
using Newtonsoft.Json;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace Tester
{
    /// <summary>
    /// Runs the existing two-bot map experiment from one JSON configuration file.
    /// The JSON contains the map grid, bot settings, simulation settings and output settings.
    /// </summary>
    public class JsonMapTester : MonoBehaviour
    {
        private const string ConfigArgument = "-mapTestConfig=";

        [Header("Configuration")]
        [SerializeField] private string configFilePath;

        [Header("Scene references")]
        [SerializeField] private GameObject botPrefab;
        [SerializeField] private GridMapManager mapManager;
        [SerializeField] private SpawnPointManager spawnPointManager;

        private readonly List<Dictionary<string, object>> results =
            new List<Dictionary<string, object>>();

        private MapTestConfiguration configuration;
        private List<KeyValuePair<string, MapTestBotMatch>> botMatches;
        private DecodedCanonicalMap decodedMap;
        private string resolvedConfigPath;
        private string configDirectory;
        private string botsDirectory;
        private string outputDirectory;

        private GameResultsAnalyzer analyzer;
        private PositionAnalyzer positionAnalyzer;
        private KillDistanceAnalyzer killDistanceAnalyzer;
        private DeathPositionAnalyzer deathPositionAnalyzer;
        private GenomeTesterGameManager manager;
        private int experimentNumber;

        private void Awake()
        {
            try
            {
                ConfigureBatchMode();
                resolvedConfigPath = ResolveConfigPath();
                configDirectory = Path.GetDirectoryName(resolvedConfigPath) ?? Directory.GetCurrentDirectory();
                configuration = ReadFromFile<MapTestConfiguration>(resolvedConfigPath);
                ValidateConfiguration(configuration);
                botMatches = new List<KeyValuePair<string, MapTestBotMatch>>(configuration.botMatches);
                botMatches.Sort((first, second) => StringComparer.Ordinal.Compare(first.Key, second.Key));

                botsDirectory = ResolveDirectory(configuration.paths.botsDirectory, configDirectory);
                outputDirectory = ResolveDirectory(configuration.paths.outputDirectory, configDirectory);
                if (!string.IsNullOrWhiteSpace(configuration.paths.outputSubdirectory))
                    outputDirectory = Path.Combine(outputDirectory, configuration.paths.outputSubdirectory);
                Directory.CreateDirectory(outputDirectory);

                decodedMap = CanonicalGridDecoder.Decode(configuration.map);
                mapManager.SetMap(decodedMap.Grid, configuration.map.mapScale);
                ConfigureVisualPlayback();

                SetupAnalyzers();
                RegisterEvents();
                StartNewExperiment();
            }
            catch (Exception exception)
            {
                FailAndQuit("Map evaluation setup failed", exception);
            }
        }

        private void OnDestroy()
        {
            StartNewExperimentGameEvent.Instance.RemoveListener(NewExperimentStarted);
            ExperimentEndedGameEvent.Instance.RemoveListener(ExperimentEnded);
        }

        private static void ConfigureBatchMode()
        {
            if (!Application.isBatchMode) return;
            Time.captureFramerate = 24;
            Application.SetStackTraceLogType(LogType.Log, StackTraceLogType.None);
        }

        private void ConfigureVisualPlayback()
        {
            if (Application.isBatchMode) return;

            var camera = Camera.main;
            if (camera != null)
            {
                var width = decodedMap.Grid.GetLength(1) * configuration.map.mapScale;
                var depth = decodedMap.Grid.GetLength(0) * configuration.map.mapScale;
                var height = mapManager.GetMapAssembler().GetWallHeight() + Mathf.Max(width, depth);
                camera.transform.SetPositionAndRotation(
                    new Vector3(width / 2f, height, depth / 2f), Quaternion.Euler(90f, 0f, 0f));
                camera.orthographic = true;
                camera.orthographicSize = 0.55f * Mathf.Max(depth, width / Mathf.Max(camera.aspect, 0.1f));
                camera.farClipPlane = height + 100f;
            }

            // The batch-test scene has no active light. Only change presentation;
            // keep the ceiling, colliders, NavMesh and bot simulation intact.
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.6f, 0.6f, 0.6f);
            var light = new GameObject("Playback Light").AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            light.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
            Debug.Log("Visual playback enabled: overhead camera fitted to the map and lighting enabled.");
        }

        private void SetupAnalyzers()
        {
            var pair = botMatches[0].Value;
            analyzer = new GameResultsAnalyzer(pair.bot1.id, pair.bot2.id);
            analyzer.Setup();

            if (configuration.logging.logPositions)
            {
                positionAnalyzer = new PositionAnalyzer(pair.bot1.id, pair.bot2.id);
                positionAnalyzer.Setup();
            }

            if (configuration.logging.logKillDistances)
            {
                killDistanceAnalyzer = new KillDistanceAnalyzer(pair.bot1.id, pair.bot2.id);
                killDistanceAnalyzer.Setup();
            }

            if (configuration.logging.logDeathPositions)
            {
                deathPositionAnalyzer = new DeathPositionAnalyzer(pair.bot1.id, pair.bot2.id);
                deathPositionAnalyzer.Setup();
            }
        }

        private void RegisterEvents()
        {
            StartNewExperimentGameEvent.Instance.AddListener(NewExperimentStarted);
            ExperimentEndedGameEvent.Instance.AddListener(ExperimentEnded);
        }

        private void StartNewExperiment()
        {
            analyzer.Reset();

            var match = botMatches[experimentNumber / configuration.numExperiments];
            if (positionAnalyzer != null) positionAnalyzer.BotMatchId = match.Key;
            if (deathPositionAnalyzer != null) deathPositionAnalyzer.BotMatchId = match.Key;
            if (killDistanceAnalyzer != null) killDistanceAnalyzer.BotMatchId = match.Key;
            var pair = match.Value;
            var bot1 = LoadBot(pair.bot1);
            var bot2 = LoadBot(pair.bot2);

            manager = gameObject.AddComponent<GenomeTesterGameManager>();
            manager.SetInitialSpawnAssignment((experimentNumber % configuration.numExperiments) % 2 != 0);
            manager.SetParameters(
                botPrefab,
                pair.bot1.id,
                bot1.Item1,
                bot1.Item2,
                pair.bot2.id,
                bot2.Item1,
                bot2.Item2,
                mapManager,
                spawnPointManager,
                configuration.gameLength,
                configuration.readyDuration,
                configuration.scoreDuration,
                configuration.respawnDuration
            );
        }

        private Tuple<BotCharacteristics, bool[]> LoadBot(MapTestBotConfiguration bot)
        {
            JSonBotCharacteristics parameters;
            bool[] guns;

            if (bot.parameters != null)
            {
                parameters = bot.parameters;
            }
            else
            {
                var paramsPath = ResolveBotFile(bot.paramsFile, bot.file, "_params.json");
                parameters = ReadFromFile<JSonBotCharacteristics>(paramsPath);
            }

            if (bot.guns != null && bot.guns.Length > 0)
            {
                guns = bot.guns;
            }
            else
            {
                var gunsPath = ResolveBotFile(bot.gunsFile, bot.file, "_guns.json");
                guns = ReadFromFile<bool[]>(gunsPath);
            }

            if (guns.Length != 4)
                throw new ArgumentException("A bot guns array must contain four boolean values.");

            return new Tuple<BotCharacteristics, bool[]>(
                new BotCharacteristics(bot.skill, parameters),
                guns
            );
        }

        private string ResolveBotFile(string explicitFile, string prefix, string suffix)
        {
            var path = explicitFile;
            if (string.IsNullOrWhiteSpace(path))
            {
                if (string.IsNullOrWhiteSpace(prefix))
                    throw new ArgumentException("A bot requires inline settings, explicit files, or a file prefix.");
                path = prefix + suffix;
            }

            return ResolveFile(path, botsDirectory);
        }

        private void ExperimentEnded()
        {
            Debug.Log("Experiment number " + experimentNumber + " ended.");

            manager.StopGame();
            Destroy(manager);
            var result = analyzer.CompileResults(configuration.gameLength);
            result["bot_match_id"] = botMatches[experimentNumber / configuration.numExperiments].Key;
            result["initial_spawn_index_bot1"] = manager.InitialSpawnIndexBot1;
            result["initial_spawn_index_bot2"] = manager.InitialSpawnIndexBot2;
            results.Add(result);
            experimentNumber++;

            if (experimentNumber >= configuration.numExperiments * botMatches.Count)
            {
                ExportAllResults();
                QuitApplication(0);
                return;
            }

            mapManager.ResetMap();
            spawnPointManager.Reset();
            StartCoroutine(WaitAndStart());
        }

        private void ExportAllResults()
        {
            var name = SafeFileName(configuration.experimentName);

            if (configuration.logging.logKillDistances)
            {
                var compiled = killDistanceAnalyzer.CompileResultsAsCSV();
                ExportResults(compiled.Item1, "kill_distances_" + name + "_bot1", ".csv");
                ExportResults(compiled.Item2, "kill_distances_" + name + "_bot2", ".csv");
            }

            if (configuration.logging.logDeathPositions)
            {
                var compiled = deathPositionAnalyzer.CompileResultsAsCSV();
                ExportResults(compiled.Item1, "death_positions_" + name + "_bot1", ".csv");
                ExportResults(compiled.Item2, "death_positions_" + name + "_bot2", ".csv");
            }

            if (configuration.logging.logPositions)
            {
                var compiled = positionAnalyzer.CompileResultsAsCSV();
                ExportResults(compiled.Item1, "position_" + name + "_bot1", ".csv");
                ExportResults(compiled.Item2, "position_" + name + "_bot2", ".csv");
            }

            if (configuration.logging.saveMap)
                ExportResults(decodedMap.NormalizedText, "map_" + name, ".txt");

            ExportResults(File.ReadAllText(resolvedConfigPath), "config_" + name, ".json");
            ExportResults(
                JsonConvert.SerializeObject(results, Formatting.Indented),
                "final_results_" + name,
                ".json"
            );
        }

        private void ExportResults(string content, string fileName, string extension)
        {
            Directory.CreateDirectory(outputDirectory);
            var filePath = Path.Combine(outputDirectory, fileName + extension);
            Debug.Log("Writing to file " + filePath);
            File.WriteAllText(filePath, content);
        }

        private IEnumerator WaitAndStart()
        {
            yield return new WaitForSeconds(0.2f);
            StartNewExperiment();
        }

        private void NewExperimentStarted()
        {
            Debug.Log("Experiment number " + experimentNumber + " started.");
        }

        private string ResolveConfigPath()
        {
            var selected = configFilePath;
            foreach (var argument in Environment.GetCommandLineArgs())
                if (argument.StartsWith(ConfigArgument, StringComparison.Ordinal))
                    selected = argument.Substring(ConfigArgument.Length);

            if (string.IsNullOrWhiteSpace(selected))
                throw new ArgumentException(
                    "Supply a JSON file through -mapTestConfig=<path> or the scene inspector."
                );

            if (Path.IsPathRooted(selected) && File.Exists(selected))
                return Path.GetFullPath(selected);

            var currentDirectoryCandidate = Path.GetFullPath(selected);
            if (File.Exists(currentDirectoryCandidate)) return currentDirectoryCandidate;

            var streamingAssetsCandidate = Path.Combine(Application.streamingAssetsPath, selected);
            if (File.Exists(streamingAssetsCandidate)) return Path.GetFullPath(streamingAssetsCandidate);

            throw new FileNotFoundException("Map test configuration is missing.", selected);
        }

        private static string ResolveDirectory(string path, string baseDirectory)
        {
            if (string.IsNullOrWhiteSpace(path)) return baseDirectory;
            return Path.IsPathRooted(path)
                ? Path.GetFullPath(path)
                : Path.GetFullPath(Path.Combine(baseDirectory, path));
        }

        private static string ResolveFile(string path, string baseDirectory)
        {
            var resolved = Path.IsPathRooted(path)
                ? Path.GetFullPath(path)
                : Path.GetFullPath(Path.Combine(baseDirectory, path));
            if (!File.Exists(resolved)) throw new FileNotFoundException("Required JSON file is missing.", resolved);
            return resolved;
        }

        private static T ReadFromFile<T>(string filePath)
        {
            Debug.Log("Reading from " + filePath);
            var json = File.ReadAllText(filePath);
            var value = JsonConvert.DeserializeObject<T>(json);
            if (value == null) throw new InvalidDataException("JSON deserialization returned null for " + filePath);
            return value;
        }

        private static void ValidateConfiguration(MapTestConfiguration config)
        {
            if (config == null) throw new ArgumentNullException(nameof(config));
            if (config.map == null) throw new ArgumentException("The configuration requires a map object.");
            if (config.botMatches == null)
                config.botMatches = new Dictionary<string, MapTestBotMatch>
                {
                    { "1", new MapTestBotMatch { bot1 = config.bot1, bot2 = config.bot2 } }
                };
            if (config.botMatches.Count == 0)
                throw new ArgumentException("bot_matches must contain at least one pair.");
            MapTestBotMatch firstPair = null;
            foreach (var entry in config.botMatches)
            {
                var pair = entry.Value;
                if (string.IsNullOrWhiteSpace(entry.Key) || pair == null || pair.bot1 == null || pair.bot2 == null)
                    throw new ArgumentException("Each bot_matches entry requires an ID, bot1 and bot2.");
                if (pair.bot1.id == 0) pair.bot1.id = 1;
                if (pair.bot2.id == 0) pair.bot2.id = 2;
                if (pair.bot1.id == pair.bot2.id)
                    throw new ArgumentException("bot1 and bot2 require different identifiers.");
                if (firstPair != null && (pair.bot1.id != firstPair.bot1.id || pair.bot2.id != firstPair.bot2.id))
                    throw new ArgumentException("All bot matches must use the same bot1 and bot2 identifiers.");
                firstPair = pair;
                foreach (var bot in new[] { pair.bot1, pair.bot2 })
                    if (float.IsNaN(bot.skill) || bot.skill < 0 || bot.skill > 1)
                        throw new ArgumentException("Bot skill values must be between 0 and 1.");
            }
            if (config.numExperiments < 1)
                throw new ArgumentException("num_experiments must be at least 1.");
            if (config.gameLength < 1)
                throw new ArgumentException("game_length must be at least 1 second.");
            if (config.map.mapScale <= 0)
                throw new ArgumentException("map_scale must be greater than 0.");
            if (string.IsNullOrWhiteSpace(config.experimentName))
                config.experimentName = config.map.mapId;
            if (config.paths == null) config.paths = new MapTestPaths();
            if (config.logging == null) config.logging = new MapTestLogging();
        }

        private static string SafeFileName(string value)
        {
            var safe = value;
            foreach (var invalid in Path.GetInvalidFileNameChars())
                safe = safe.Replace(invalid, '_');
            return safe;
        }

        private static void FailAndQuit(string message, Exception exception)
        {
            Debug.LogError(message + ": " + exception);
            QuitApplication(-1);
        }

        private static void QuitApplication(int exitCode)
        {
#if UNITY_EDITOR
            EditorApplication.isPlaying = false;
#else
            Application.Quit(exitCode);
#endif
        }
    }
}
