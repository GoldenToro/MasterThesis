using Events;

namespace Logging
{
    // Timestamps are scaled seconds since the bot first enters active gameplay.
    public struct PickupLogEntry
    {
        public float timeSeconds;
        public int entityId;
        public int pickupId;
        public string pickupType;
        public float x;
        public float z;
        public int healthBefore;
        public int healthAfter;
        public int maxHealth;
        public int healthRestored;
    }

    public struct AliveInterval
    {
        public float startSeconds;
        public float endSeconds;
    }

    /// <summary>
    /// Represents the game metrics as calculated by an entity.
    /// </summary>
    public struct GameMetrics
    {
        public int entityId;

        public float timeToEngage;

        public int numberOfFights;
        public float timeInFights;

        public int numberOfRetreats;
        public float timeToSurrender;

        public int numberOfSights;
        public float timeBetweenSights;

        public PickupLogEntry[] pickupEvents;
        public AliveInterval[] aliveIntervals;
        public float aliveTime;
    }

    public class BaseEntityGameMetricsGameEvent : GameEventBase<GameMetrics>
    {
    }

    public class EntityGameMetricsGameEvent : ClassSingleton<BaseEntityGameMetricsGameEvent>
    {
    }
}
