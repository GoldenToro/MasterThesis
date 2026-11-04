using AI.Layers.KnowledgeBase;
using Bonsai;
using Bonsai.CustomNodes;
using UnityEngine;

namespace AI.BonsaiBehaviours.Conditions
{
    /// <summary>
    /// Runs the camping branch while waiting, then succeeds when the pickup is expected to be available.
    /// </summary>
    [BonsaiNode("Conditional/")]
    public class ShouldGoToPickup : TimedEvaluationConditionalAbort
    {
        private PickupPlanner pickupPlanner;

        public override void OnStart()
        {
            pickupPlanner = Actor.GetComponent<AIEntity>().PickupPlanner;
        }

        public override bool Condition()
        {
            return Time.time < pickupPlanner.GetChosenPickupEstimatedActivationTime();
        }

        public override Status Run()
        {
            if (!Condition()) return Status.Success;

            // Keep moving nearby if the previous camping path finished before the pickup respawned.
            Iterator.Traverse(Child);
            return Status.Running;
        }
    }
}
