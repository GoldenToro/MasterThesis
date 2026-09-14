using System;
using AI.Layers.KnowledgeBase;
using AI.Layers.SensingLayer;
using AI.Layers.Sensors;
using Bonsai.Core;
using Logging;
using UnityEngine;

namespace AI.GoalMachine.Goal
{
    /// <summary>
    /// Search enemy goal.
    /// Deals with searching/predicting the position of the enemy and reaching it.
    /// The goal plan is contained in a behaviour tree.
    /// </summary>
    public class SearchEnemy : IGoal
    {
        private const float NO_TIME = -1;
        private readonly TargetKnowledgeBase _targetKnowledgeBase;
        private readonly DamageSensor damageSensor;
        private readonly AIEntity entity; 
        private readonly SoundSensor soundSensor;
        private readonly RespawnSensor respawnSensor;
        private Recklessness _recklessness;
        private bool resetInUpdate;

        private BonsaiTreeComponent bonsaiBehaviorTree;
        private readonly BehaviourTree blueprint;
        
        private float searchTriggeringEventTime = NO_TIME;

        public SearchEnemy(AIEntity entity)
        {
            this.entity = entity;
            _targetKnowledgeBase = entity.TargetKnowledgeBase;
            _recklessness = entity.Characteristics.Recklessness;
            damageSensor = entity.DamageSensor;
            soundSensor = entity.SoundSensor;
            respawnSensor = entity.RespawnSensor;
            blueprint = Resources.Load<BehaviourTree>("Behaviors/BonsaiSearchEnemy");
            bonsaiBehaviorTree = entity.gameObject.AddComponent<BonsaiTreeComponent>();
            bonsaiBehaviorTree.SetBlueprint(blueprint);
        }
        
        public float GetScore()
        {
            if (!entity.GetEnemy().IsAlive || _targetKnowledgeBase.HasDetectedTarget())
            {
                // Debug.Log("Entity " + entity.GetID() + " Search score is 0 (dead or seen)");
                return 0f;
            }

            var mostRecentEvent = MostRecentEventTimeOrNoTime();

            if (mostRecentEvent == NO_TIME)
            {
                // Debug.Log("Entity " + entity.GetID() + " Search score is 0 (no events)");
                return 0f;
            }

            var maxScore = _recklessness switch
            {
                Recklessness.Low => 0.6f,
                Recklessness.Neutral => 0.85f,
                Recklessness.High => 1.0f,
                _ => throw new ArgumentOutOfRangeException()
            };


            var score = Mathf.Max(maxScore - (Time.time - mostRecentEvent) / 10f, 0f);

            if (searchTriggeringEventTime != NO_TIME && searchTriggeringEventTime != mostRecentEvent)
            {
                // I'm already searching but I received a new event. Forcibly cause update
                resetInUpdate = true;
            }
            else
            {
                resetInUpdate = false;
            }

            // Debug.Log("Entity " + entity.GetID() + " Search score is " + score);
            return score;
        }

        public void Enter()
        {
            bonsaiBehaviorTree.Reset();
            FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo
                {entityID = entity.GetID(), isFocusing = true}
            );
            searchTriggeringEventTime = MostRecentEventTimeOrNoTime();
        }

        public void Update()
        {
            if (resetInUpdate)
            {
                Exit();
                Enter();
            }

            bonsaiBehaviorTree.Tick();
        }

        public void Exit()
        {
            searchTriggeringEventTime = NO_TIME;
            FocusingOnEnemyGameEvent.Instance.Raise(
                new FocusOnEnemyInfo {entityID = entity.GetID(), isFocusing = false});
            bonsaiBehaviorTree.Reset();

        }

        private float RecentLossTimeOrNoTime()
        {
            return _targetKnowledgeBase.HasLostTarget() ? _targetKnowledgeBase.LastTimeDetected : NO_TIME;
        }

        private float LastRecentDamageTimeOrNoTime()
        {
            return damageSensor.WasDamagedRecently ? damageSensor.LastTimeDamaged : NO_TIME;
        }

        private float LastRecentNoiseTimeOrNoTime()
        {
            return soundSensor.HeardShotRecently ? soundSensor.LastTimeHeardShot : NO_TIME;
        }

        private float RecentRespawnTimeOrNoTime()
        {
            return respawnSensor.DetectedRespawnRecently ? respawnSensor.LastRespawnTime : NO_TIME;
        }

        private float MostRecentEventTimeOrNoTime()
        {
            var timeNoise = LastRecentNoiseTimeOrNoTime();
            var timeDamage = LastRecentDamageTimeOrNoTime();
            var timeLost = RecentLossTimeOrNoTime();
            var timeRespawn = RecentRespawnTimeOrNoTime(); 
            return Mathf.Max(
                Mathf.Max(searchTriggeringEventTime, timeNoise), 
                Mathf.Max(timeDamage, Mathf.Max(timeLost, timeRespawn))
            );
        }
    }
}