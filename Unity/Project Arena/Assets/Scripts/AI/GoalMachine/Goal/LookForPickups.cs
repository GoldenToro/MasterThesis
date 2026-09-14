using System;
using AI.Layers.KnowledgeBase;
using Bonsai.Core;
using Pickables;
using UnityEngine;

namespace AI.GoalMachine.Goal
{
    /// <summary>
    /// Pickup goal.
    /// Deals with selecting and reaching a pickup, plus fighting the enemy if required.
    /// The goal plan is contained in a behaviour tree.
    /// </summary>
    public class LookForPickups : IGoal
    {
        private readonly AIEntity entity;
        private BonsaiTreeComponent bonsaiBehaviorTree;
        private readonly BehaviourTree blueprint;
        
        private readonly PickupPlanner pickupPlanner;
        private readonly float scoreMultiplier = 0.7f;
        private Pickable currentPickable;
        private Pickable nextPickable;

        public LookForPickups(AIEntity entity)
        {
            this.entity = entity;
            pickupPlanner = entity.PickupPlanner;
            var recklessness = entity.Characteristics.Recklessness;
            switch (recklessness)
            {
                case Recklessness.Low:
                    scoreMultiplier *= 1.3f;
                    break;
                case Recklessness.Neutral:
                    break;
                case Recklessness.High:
                    scoreMultiplier /= 1.3f;
                    break;
                default:
                    throw new ArgumentOutOfRangeException();
            }

            blueprint = Resources.Load<BehaviourTree>("Behaviors/BonsaiPickup");
            bonsaiBehaviorTree = entity.gameObject.AddComponent<BonsaiTreeComponent>();
            bonsaiBehaviorTree.SetBlueprint(blueprint);
        }

        public float GetScore()
        {
            nextPickable = pickupPlanner.GetChosenPickup();
            return scoreMultiplier * pickupPlanner.GetChosenPickupScore();
        }


        public void Enter()
        {
            // Do not enable behavior, it will be done in Update!
            currentPickable = null;
        }

        public void Update()
        {
            if (currentPickable != nextPickable)
            {
                if (currentPickable != null)
                {
                    bonsaiBehaviorTree.Reset();
                }

                bonsaiBehaviorTree.Reset();
                currentPickable = nextPickable;
            }

            bonsaiBehaviorTree.Tick();

            if (!bonsaiBehaviorTree.IsRunning())
            {
                pickupPlanner.ForceUpdate();
                bonsaiBehaviorTree.Reset();
                currentPickable = null;
            }
            
        }

        public void Exit()
        {
            bonsaiBehaviorTree.Reset();
        }
    }
}