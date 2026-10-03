using System.Collections.Generic;
using System.Linq;
using Logging;
using UnityEngine;
using Utils;

namespace Tester
{
    /// <summary>
    /// Collects game statistics events and compiles them into their final results.
    /// </summary>
    public class GameResultsAnalyzer
    {
        private readonly int bot1ID;
        private readonly int bot2ID;
        private readonly Dictionary<int, int> currentKillStreak = new();
        private readonly Dictionary<int, int> killStreakMax = new();
        private readonly Dictionary<int, int> killStreaksSum = new();

        private readonly Dictionary<int, int> nonZeroKillStreaksCount = new();

        private readonly Dictionary<int, int> numberOfFights = new();

        private readonly Dictionary<int, int> numberOfSights = new();

        private readonly Dictionary<int, int> numberOfFrags = new();

        private readonly Dictionary<int, int> numberOfHits = new();

        private readonly Dictionary<int, int> numberOfRetreats = new();

        private readonly Dictionary<int, int> numberOfShots = new();

        private readonly Dictionary<int, int> numberOfProjectiles = new();

        private readonly Dictionary<int, int> numberOfSuicides = new();

        private readonly Dictionary<int, float> timeBetweenSights = new();

        private readonly Dictionary<int, float> timeInFight = new();

        private readonly Dictionary<int, float> timeToEngage = new();

        private readonly Dictionary<int, float> timeToSurrender = new();

        public GameResultsAnalyzer(int bot1ID, int bot2ID)
        {
            this.bot1ID = bot1ID;
            this.bot2ID = bot2ID;
        }

        public void Setup()
        {
            EntityGameMetricsGameEvent.Instance.AddListener(LogMetrics);
            KillInfoGameEvent.Instance.AddListener(LogKill);
            ShotInfoGameEvent.Instance.AddListener(LogShot);
            HitInfoGameEvent.Instance.AddListener(LogHit);
        }

        public void TearDown()
        {
            EntityGameMetricsGameEvent.Instance.RemoveListener(LogMetrics);
            KillInfoGameEvent.Instance.RemoveListener(LogKill);
            ShotInfoGameEvent.Instance.RemoveListener(LogShot);
            HitInfoGameEvent.Instance.RemoveListener(LogHit);
        }

        public void Reset()
        {
            timeToEngage.Clear();
            numberOfFights.Clear();
            timeInFight.Clear();
            numberOfRetreats.Clear();
            timeToSurrender.Clear();
            timeBetweenSights.Clear();

            numberOfFrags.Clear();
            numberOfSuicides.Clear();
            numberOfShots.Clear();
            numberOfProjectiles.Clear();
            numberOfHits.Clear();
            numberOfSights.Clear();
            killStreakMax.Clear();
            killStreaksSum.Clear();
            currentKillStreak.Clear();
            nonZeroKillStreaksCount.Clear();
        }

        private void LogMetrics(GameMetrics receivedInfo)
        {
            timeToEngage.Add(receivedInfo.entityId, receivedInfo.timeToEngage);
            numberOfFights.Add(receivedInfo.entityId, receivedInfo.numberOfFights);
            timeInFight.Add(receivedInfo.entityId, receivedInfo.timeInFights);
            numberOfRetreats.Add(receivedInfo.entityId, receivedInfo.numberOfRetreats);
            timeToSurrender.Add(receivedInfo.entityId, receivedInfo.timeToSurrender);
            timeBetweenSights.Add(receivedInfo.entityId, receivedInfo.timeBetweenSights);
            numberOfSights.Add(receivedInfo.entityId, receivedInfo.numberOfSights);
        }

        private void LogHit(HitInfo receivedInfo)
        {
            numberOfHits.AddToKey(receivedInfo.hitterEntityID, 1);
        }

        private void LogShot(ShotInfo receivedInfo)
        {
            numberOfShots.AddToKey(receivedInfo.ownerId, 1);
            numberOfProjectiles.AddToKey(receivedInfo.ownerId, receivedInfo.projectilesPerShot);
        }

        private void LogKill(KillInfo receivedInfo)
        {
            if (receivedInfo.killedEntityID == receivedInfo.killerEntityID)
            {
                // Suicide!
                CloseKillStreak(receivedInfo.killedEntityID);
                numberOfSuicides.AddToKey(receivedInfo.killedEntityID, 1);
                return;
            }

            numberOfFrags.AddToKey(receivedInfo.killerEntityID, 1);
            // TODO This is slightly wrong, what if I have a reciprocal kill? 
            // One of the entities would get the point now, and the other only after death.

            // Update killer streak info
            if (currentKillStreak.TryGetValue(receivedInfo.killerEntityID, out var currentStreak))
            {
                // Already started a streak, update value!
                currentKillStreak[receivedInfo.killerEntityID] = currentStreak + 1;
            }
            else
            {
                // No streak! Start a new one
                currentKillStreak[receivedInfo.killerEntityID] = 1;
                nonZeroKillStreaksCount.AddToKey(receivedInfo.killerEntityID, 1);
            }

            CloseKillStreak(receivedInfo.killedEntityID);
        }

        private void CloseKillStreak(int entityId)
        {
            // Update killed streak info
            if (currentKillStreak.TryGetValue(entityId, out var streak))
            {
                // The entity had a streak! Interrupt it now.
                killStreaksSum.AddToKey(entityId, streak);
                currentKillStreak.Remove(entityId);

                // Update max kill streak if needed
                var hadMax = killStreakMax.TryGetValue(entityId, out var max);
                if (!hadMax || streak > max) killStreakMax[entityId] = streak;
            }
        }

        public Dictionary<string, object> CompileResults(float gameLength)
        {
            // Accuracy is hits per projectile. No projectiles means unavailable.
            var accuracy = new Dictionary<int, float?>();
            foreach (var botID in new[] { bot1ID, bot2ID })
            {
                numberOfProjectiles.TryGetValue(botID, out var projectiles);
                numberOfHits.TryGetValue(botID, out var hits);
                accuracy[botID] = projectiles > 0
                    ? (float?) hits / projectiles
                    : null;
            }
            var killStreakAverage = new Dictionary<int, float?>();
            foreach (var key in nonZeroKillStreaksCount.Keys)
            {
                CloseKillStreak(key);
                var count = nonZeroKillStreaksCount[key];
                killStreaksSum.TryGetValue(key, out var sum);
                killStreakAverage.Add(key, sum / (float) count);
            }

            var totalFrags = numberOfFrags.Sum(entry => entry.Value);
            float? entropy = totalFrags > 0
                ? (float?) numberOfFrags
                    .Where(entry => entry.Value > 0)
                    .Sum(entry =>
                    {
                        var probability = entry.Value / (float) totalFrags;
                        return -probability * Mathf.Log(probability, 2);
                    })
                : null;

            var numberOfFightsSum = numberOfFights.Sum(entry => entry.Value);
            var timeToEngageSum = timeToEngage.Sum(entry => entry.Value);
            float? pace = timeToEngageSum > 0
                ? (float?) (
                    2f / (1f + Mathf.Exp(-5f * numberOfFightsSum / timeToEngageSum)) - 1f
                )
                : null;

            var timeInFightSum = timeInFight.Sum(entry => entry.Value);
            var timeBetweenSightsSum = timeBetweenSights.Sum(entry => entry.Value);
            var timeToSurrenderSum = timeToSurrender.Sum(entry => entry.Value);
            var numberOfRetreatsSum = numberOfRetreats.Sum(entry => entry.Value);

            var pursueTime = timeInFightSum / (2 * gameLength);
            var fightTime =
                (timeInFightSum - timeBetweenSightsSum - timeToSurrenderSum)
                / (2 * gameLength);

            float? sightLossRate = timeInFightSum > 0
                ? (float?) timeBetweenSightsSum / timeInFightSum
                : null;

            float? targetLossRate = numberOfFightsSum > 0
                ? (float?) numberOfRetreatsSum / numberOfFightsSum
                : null;
            var compiled = new Dictionary<string, object>
            {
                {"timeInFight1", timeInFight.GetOrDefault(bot1ID)},
                {"timeInFight2", timeInFight.GetOrDefault(bot2ID)},
                {"timeToEngage1", timeToEngage.GetOrDefault(bot1ID)},
                {"timeToEngage2", timeToEngage.GetOrDefault(bot2ID)},
                {"numberOfFights1", numberOfFights.GetOrDefault(bot1ID)},
                {"numberOfFights2", numberOfFights.GetOrDefault(bot2ID)},
                {"numberOfSights1", numberOfSights.GetOrDefault(bot1ID)},
                {"numberOfSights2", numberOfSights.GetOrDefault(bot2ID)},
                {"timeBetweenSights1", timeBetweenSights.GetOrDefault(bot1ID)},
                {"timeBetweenSights2", timeBetweenSights.GetOrDefault(bot2ID)},
                {"timeToSurrender1", timeToSurrender.GetOrDefault(bot1ID)},
                {"timeToSurrender2", timeToSurrender.GetOrDefault(bot2ID)},
                {"numberOfRetreats1", numberOfRetreats.GetOrDefault(bot1ID)},
                {"numberOfRetreats2", numberOfRetreats.GetOrDefault(bot2ID)},
                {"numberOfFrags1", numberOfFrags.GetOrDefault(bot1ID)},
                {"numberOfFrags2", numberOfFrags.GetOrDefault(bot2ID)},
                {"numberOfSuicides1", numberOfSuicides.GetOrDefault(bot1ID)},
                {"numberOfSuicides2", numberOfSuicides.GetOrDefault(bot2ID)},
                {"numberOfShots1", numberOfShots.GetOrDefault(bot1ID)},
                {"numberOfShots2", numberOfShots.GetOrDefault(bot2ID)},
                {"numberOfProjectiles1", numberOfProjectiles.GetOrDefault(bot1ID)},
                {"numberOfProjectiles2", numberOfProjectiles.GetOrDefault(bot2ID)},
                {"numberOfHits1", numberOfHits.GetOrDefault(bot1ID)},
                {"numberOfHits2", numberOfHits.GetOrDefault(bot2ID)},
                {"accuracy1", accuracy.GetOrDefault(bot1ID)},
                {"accuracy2", accuracy.GetOrDefault(bot2ID)},
                {"killStreakAverage1", killStreakAverage.GetOrDefault(bot1ID)},
                {"killStreakAverage2", killStreakAverage.GetOrDefault(bot2ID)},
                {"killStreakMax1", killStreakMax.GetOrDefault(bot1ID)},
                {"killStreakMax2", killStreakMax.GetOrDefault(bot2ID)},
                {"entropy", entropy},
                {"pace", pace},
                {"fightTime", fightTime},
                {"pursueTime", pursueTime},
                {"sightLossRate", sightLossRate},
                {"targetLossRate", targetLossRate}
            };
            foreach (var key in compiled.Keys.ToArray())
            {
                if (compiled[key] is float value &&
                    (float.IsNaN(value) || float.IsInfinity(value)))
                {
                    compiled[key] = null;
                }
            }

            return compiled;
        }
    }
}