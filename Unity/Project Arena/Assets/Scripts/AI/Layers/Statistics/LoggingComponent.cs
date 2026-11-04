using System;
using System.Collections.Generic;
using System.Linq;
using Logging;
using Pickables;
using UnityEngine;

namespace AI.Layers.Statistics
{
    /// <summary>
    /// Takes care of logging information about Entity-relavant events (such as spotting an enemy) in order to
    /// facilitate compiling this information for logging purposes.
    /// </summary>
    public class LoggingComponent
    {
        private readonly AIEntity entity;

        private readonly List<PickupLogEntry> pickupEvents = new();
        private readonly List<AliveInterval> aliveIntervals = new();
        private float? activeMatchStart;
        private float? aliveIntervalStart;
        private float totalAliveTime;
        private bool resourceLoggingEnded;

        private bool loggedFirstRespawn;

        private float lastRespawnTime;
        private float currentFightStartTime;
        private float previousFightEndTime;

        private int numberOfFights;
        private int numberOfRetreats;

        private float totalTimeBetweenSights;

        private float totalTimeInFight;

        private float totalTimeToEngage;

        private int numberOfSights;

        private float totalTimeToSurrender;

        // Focusing status of the current frame.
        // It might change any time and any amount of time between calls to Update()
        private bool isInCombat;

        // Focusing status of the previous frame
        private bool previouslyWasInCombat;

        private bool wasEnemyVisibleLastFrame;
        private float enemySightLossTime;
        
        public LoggingComponent(AIEntity entity)
        {
            this.entity = entity;
            lastRespawnTime = Time.time;
            SpawnInfoGameEvent.Instance.AddListener(RespawnEvent);
            FocusingOnEnemyGameEvent.Instance.AddListener(FocusingEvent);
        }


        public void LogActiveState(bool active)
        {
            if (resourceLoggingEnded) return;
            if (active)
            {
                if (!activeMatchStart.HasValue) activeMatchStart = Time.time;
                if (!aliveIntervalStart.HasValue)
                    aliveIntervalStart = Time.time - activeMatchStart.Value;
            }
            else if (aliveIntervalStart.HasValue)
            {
                var end = Mathf.Max(aliveIntervalStart.Value, Time.time - activeMatchStart.Value);
                aliveIntervals.Add(new AliveInterval
                {
                    startSeconds = aliveIntervalStart.Value,
                    endSeconds = end
                });
                totalAliveTime += end - aliveIntervalStart.Value;
                aliveIntervalStart = null;
            }
        }

        public void LogPickup(Pickable pickup, int healthBefore)
        {
            if (resourceLoggingEnded || !aliveIntervalStart.HasValue) return;
            var position = pickup.transform.position;
            var healthAfter = entity.Health;
            pickupEvents.Add(new PickupLogEntry
            {
                timeSeconds = Time.time - activeMatchStart.Value,
                entityId = entity.GetID(),
                pickupId = pickup.GetInstanceID(),
                pickupType = pickup.GetPickupType().ToString(),
                x = position.x,
                z = position.z,
                healthBefore = healthBefore,
                healthAfter = healthAfter,
                maxHealth = entity.MaxHealth,
                // Exclude overfill and recovery of negative, overkill health.
                healthRestored = Mathf.Max(0,
                    Mathf.Clamp(healthAfter, 0, entity.MaxHealth) -
                    Mathf.Clamp(healthBefore, 0, entity.MaxHealth))
            });
        }

        // TODO Combat event might start even if enemy is not visible
        // TODO I might give up search before even detecting the enemy in the first place, so the total time to
        //   surrender is wrong
        public void Update()
        {
            if (previouslyWasInCombat != isInCombat)
            {
                // Debug.Log(entity.name + " changed focusing to " + isFocusingOnEnemy);
                if (isInCombat)
                {
                    // I am now in combat event
                    currentFightStartTime = Time.time;
                    totalTimeToEngage += currentFightStartTime - Mathf.Max(lastRespawnTime, previousFightEndTime);
                    numberOfFights++;
                }
                else
                {
                    // I am no longer in combat event
                    previousFightEndTime = Time.time;
                    totalTimeInFight += previousFightEndTime - currentFightStartTime;
                    if (entity.IsAlive && entity.GetEnemy().IsAlive)
                    {
                        // I am no longer in combat but we are both alive. Did I gave up on searching?
                        totalTimeToSurrender += Time.time - Math.Max(currentFightStartTime, entity.TargetKnowledgeBase.LastTimeDetected);
                        numberOfRetreats++; 
                    }
                }
                previouslyWasInCombat = isInCombat;
            }

            var enemyInfo = entity.TargetMemory.GetEnemyInfo();
            if (enemyInfo.Count == 0) return;
            var isCurrentlyVisible = enemyInfo.Last().isVisible;
            if (isInCombat)
            {
                if (wasEnemyVisibleLastFrame != isCurrentlyVisible)
                {
                    // Debug.Log(entity.name + " changed target sight to " + isCurrentlyVisible);
                    if (!isCurrentlyVisible)
                    {
                        // Enemy sight lost
                        enemySightLossTime = Time.time;
                    }
                    else
                    {
                        // Enemy sight reestablished
                        totalTimeBetweenSights += Time.time - Math.Max(currentFightStartTime, enemySightLossTime);
                        numberOfSights++;
                    }
                }
            }
            wasEnemyVisibleLastFrame = isCurrentlyVisible;
        }

        public void PublishAndRelease()
        {
            LogActiveState(false);
            resourceLoggingEnded = true;
            // TODO update last time with focusing on enemy false
            EntityGameMetricsGameEvent.Instance.Raise(
                new GameMetrics
                {
                    entityId = entity.GetID(),
                    timeBetweenSights = totalTimeBetweenSights,
                    timeInFights = totalTimeInFight,
                    timeToSurrender = totalTimeToSurrender,
                    timeToEngage = totalTimeToEngage,
                    numberOfRetreats = numberOfRetreats,
                    numberOfFights = numberOfFights,
                    numberOfSights = numberOfSights,
                    pickupEvents = pickupEvents.ToArray(),
                    aliveIntervals = aliveIntervals.ToArray(),
                    aliveTime = totalAliveTime
                }
            );

            SpawnInfoGameEvent.Instance.RemoveListener(RespawnEvent);
            FocusingOnEnemyGameEvent.Instance.RemoveListener(FocusingEvent);
        }

        private void RespawnEvent(SpawnInfo info)
        {
            if (info.entityId != entity.GetID()) return;
            lastRespawnTime = Time.time;
        }

        private void FocusingEvent(FocusOnEnemyInfo info)
        {
            if (info.entityID != entity.GetID()) return;
            isInCombat = info.isFocusing;
        }
    }
}
