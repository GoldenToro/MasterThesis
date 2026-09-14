using System.Collections;
using Logging;
using Managers.Map;
using Maps.MapGenerator;
using Others;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Managers.Mode
{
    /// <summary>
    ///     GameManager is an abstract class used to define and manage a game mode. It implements an
    ///     ILoggable interface that allows to log the game.
    /// </summary>
    public abstract class GameManager : CoreComponent, ILoggable
    {
        [Header("Managers")] [SerializeField] protected MapManager mapManagerScript;
        [SerializeField] protected SpawnPointManager spawnPointManagerScript;

        [Header("Game")] [SerializeField] protected bool generateOnly;
        [SerializeField] protected int gameDuration = 600;
        [SerializeField] protected int readyDuration = 3;
        [SerializeField] protected int scoreDuration = 10;
        [SerializeField] protected float respawnDuration = 3;

        // Current phase of the game: 0 = ready, 1 = figth, 2 = score.
        protected int gamePhase = -1;

        // Do I have to handshake with the Experiment Manager?
        protected bool handshaking;

        // Is the game paused?
        protected bool isPaused = false;

        // Do I have to log?
        protected bool loggingGame;

        // Time at which the game started.
        protected float startTime;

        // Setups stuff for the loggingGame.
        public void SetupLogging()
        {
            var currentMap = mapManagerScript.GetMap();
            MapInfoGameEvent.Instance.Raise(new MapInfo
            {
                height = currentMap.GetLength(0),
                width = currentMap.GetLength(1),
                ts = mapManagerScript.GetMapAssembler().GetMapScale(),
                f = mapManagerScript.GetFlip()
            });
            GameInfoGameEvent.Instance.Raise(new GameInfo
                {
                    gameDuration = gameDuration,
                    scene = SceneManager.GetActiveScene().name
                }
            );
            loggingGame = true;
        }

        // Moves a gameobject to a free spawn point.
        public void Spawn(GameObject g)
        {
            g.transform.position = spawnPointManagerScript.GetSpawnPosition();
        }

        // Menages the death of an entity.
        public abstract void ManageEntityDeath(GameObject g, Entity.Entity e);

        protected abstract void UpdateGamePhase();

        protected abstract void ManageGame();

        public abstract void AddScore(int i, int j);

        public abstract void SetUIColor(Color c);

        public abstract void Pause();

        public IEnumerator FreezeTime(float wait, bool mustPause)
        {
            if (mustPause) yield return new WaitForSeconds(wait);

            Time.timeScale = isPaused ? 0f : 1f;
        }

        public void Quit()
        {
            Time.timeScale = 1f;
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;

            LoadNextScene("Exit");
        }

        // Loads the next scene
        private void LoadNextScene(string def)
        {
            // TODO not very clean...
            if (LoadNextSceneGameEvent.Instance.HasAnyListener() && ParameterManager.HasInstance())
                LoadNextSceneGameEvent.Instance.Raise();
            else
                SceneManager.LoadScene(def);
        }

        // Allows the Game Manager to tell the Experiment Manager when it can start to log.
        public void LoggingHandshake()
        {
            handshaking = true;
        }

        // Tells if it is loggingGame.
        public bool IsLogging()
        {
            return loggingGame;
        }

        public char[,] GetMap()
        {
            return mapManagerScript.GetMap();
        }

        public Area[] GetAreas()
        {
            return mapManagerScript.GetAreas();
        }

        public float GetMapScale()
        {
            return mapManagerScript.MapScale;
        }
    }
}