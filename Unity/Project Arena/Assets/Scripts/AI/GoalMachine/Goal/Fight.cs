using System;
using AI.Layers.KnowledgeBase;
using Bonsai.Core;
using Entity.Component;
using Logging;
using UnityEngine;

namespace AI.GoalMachine.Goal
{
    /// <summary>
    /// Fighting goal. Deals with moving, shooting, finding cover, reloading and so on.
    /// The goal plan is contained in a behaviour tree.
    /// </summary>
    public class Fight : IGoal
    {
        private const float LOW_HEALTH_PENALTY = 0.4f;
        private readonly AIEntity entity;
        private BonsaiTreeComponent bonsaiBehaviorTree;
        private readonly BehaviourTree blueprint;
        private readonly GunManager gunManager;
        private readonly TargetKnowledgeBase _targetKnowledgeBase;
        private readonly float scoreMultiplier = 1.0f;

        public Fight(AIEntity entity)
        {
            this.entity = entity;
            _targetKnowledgeBase = entity.TargetKnowledgeBase;
            var recklessness = entity.Characteristics.Recklessness;
            switch (recklessness)
            {
                case Recklessness.Low:
                    scoreMultiplier /= 1.3f;
                    break;
                case Recklessness.Neutral:
                    break;
                case Recklessness.High:
                    scoreMultiplier *= 1.3f;
                    break;
                default:
                    throw new ArgumentOutOfRangeException();
            }
            gunManager = entity.GunManager;
            blueprint = Resources.Load<BehaviourTree>("Behaviors/BonsaiFight");
            bonsaiBehaviorTree = entity.gameObject.AddComponent<BonsaiTreeComponent>();
            bonsaiBehaviorTree.SetBlueprint(blueprint);
        }

        public float GetScore()
        {
            if (!gunManager.HasAmmo()) return 0;
            var canSee = _targetKnowledgeBase.HasDetectedTarget() && entity.GetEnemy().IsAlive;
            var inverseHealthPercentage = 1f - (float) entity.Health / entity.MaxHealth;
            // Scale score based on our health. Maybe we want to run away instead of fighting.
            return canSee ? scoreMultiplier * (1.0f - inverseHealthPercentage * LOW_HEALTH_PENALTY) : 0.0f;
        }


        public void Enter()
        {
            bonsaiBehaviorTree.Reset();
            FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo {entityID = entity.GetID(), isFocusing = true});
        }

        public void Update()
        {
            // FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo {entityID = entity.GetID(), isFocusing = true});
            bonsaiBehaviorTree.Tick();
        }

        public void Exit()
        {
            FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo {entityID = entity.GetID(), isFocusing = false});
            bonsaiBehaviorTree.Reset();
            // Resources.UnloadAsset(externalBt);
            // Object.Destroy(behaviorTree);
        }
    }
}