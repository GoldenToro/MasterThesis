using System.Collections.Generic;
using System.Linq;
using Others;
using UnityEngine;

namespace Managers
{
    /// <summary>
    ///     SpawnPointManager menages the spawn points, keeping track of the last time each one of them was
    ///     used.
    /// </summary>
    public class SpawnPointManager : CoreComponent
    {
        [SerializeField] private float spawnCooldown = 5f;

        // Last used spawn point.
        private SpawnPoint lastUsed;

        // List of all the spawn points.
        private List<SpawnPoint> spawnPoints;

        public void Reset()
        {
            spawnPoints.Clear();
        }

        // Use this for initialization.
        private void Start()
        {
            spawnPoints = new List<SpawnPoint>();

            SetReady(true);
        }

        // Sets the spawn points.
        public void SetSpawnPoints(List<GameObject> SPs)
        {
            if (SPs != null && SPs.Count > 0)
                foreach (var s in SPs)
                    spawnPoints.Add(new SpawnPoint(s.transform.position, -1 * Mathf.Infinity));
            else
                ManageError(Error.HARD_ERROR, "Error while setting the spawn points, no spawn point " +
                                              "was found.");
        }

        // Updates the last used field of all the spawn points that have already been used.
        public void UpdateLastUsed()
        {
            foreach (var s in spawnPoints)
                if (s.lastUsed > -1 * Mathf.Infinity)
                    s.lastUsed = Time.time;
        }

        // Returns an available spawn position.
        public Vector3 GetSpawnPosition()
        {
            var availableSpawnPoints = spawnPoints.Where(spawnPoint =>
                Time.time - spawnPoint.lastUsed >= spawnCooldown && spawnPoint != lastUsed).ToList();

            if (availableSpawnPoints.Count == 0)
                return GetRandomSpawnPoint(spawnPoints).spawnPosition;
            return GetRandomSpawnPoint(availableSpawnPoints).spawnPosition;
        }

        public Vector3 GetAssignedSpawnPosition(int index)
        {
            if (spawnPoints == null || index < 0 || index >= spawnPoints.Count)
                throw new System.ArgumentOutOfRangeException(
                    nameof(index), "Assigned spawn is missing."
                );

            var spawnPoint = spawnPoints[index];
            spawnPoint.lastUsed = Time.time;
            lastUsed = spawnPoint;
            return spawnPoint.spawnPosition;
        }
        // Returns a random spawn point from a list.
        private SpawnPoint GetRandomSpawnPoint(List<SpawnPoint> SPs)
        {
            var index = Random.Range(0, SPs.Count);
            SPs[index].lastUsed = Time.time;
            lastUsed = SPs[index];
            return SPs[index];
        }

        private class SpawnPoint
        {
            public readonly Vector3 spawnPosition;
            public float lastUsed;

            public SpawnPoint(Vector3 sp, float lu)
            {
                spawnPosition = sp;
                lastUsed = lu;
            }
        }
    }
}