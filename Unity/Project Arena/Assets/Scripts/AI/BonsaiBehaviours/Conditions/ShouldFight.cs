using AI.Layers.KnowledgeBase;
using Bonsai;
using Bonsai.CustomNodes;
using Logging;
using UnityEngine;
using Random = UnityEngine.Random;

namespace AI.BonsaiBehaviours.Conditions
{
    /// <summary>
    /// Returns Success if we should fight the enemy, Failure otherwise.
    /// </summary>
    [BonsaiNode("Conditional/")]
    public class ShouldFight : TimedEvaluationConditionalAbort
    {
        private AIEntity entity;
        private TargetKnowledgeBase _targetKnowledgeBase;
        private const float TIMEOUT_CHANGE_IDEA = 1.5f; 
        private float timestampChangeIdeaAllowed; 
        private float probabilityFightBack;
        private bool hasDecidedToFight;

        public override void OnStart()
        {
            entity = Actor.GetComponent<AIEntity>();
            _targetKnowledgeBase = entity.TargetKnowledgeBase;
            probabilityFightBack = entity.Characteristics.FightBackWhenCollectingPickup;
        }

        public override bool Condition()
        {
            if (!_targetKnowledgeBase.HasDetectedTarget())
            {
                hasDecidedToFight = false;
                FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo {entityID = entity.GetID(), isFocusing = false});
                return false;
            }

            if (Time.time < timestampChangeIdeaAllowed)
            {
                // I won't change my decision for now.
                return hasDecidedToFight;
            }

            timestampChangeIdeaAllowed = Time.time + TIMEOUT_CHANGE_IDEA;
            hasDecidedToFight = Random.value <= probabilityFightBack;
            FocusingOnEnemyGameEvent.Instance.Raise(new FocusOnEnemyInfo
                {entityID = entity.GetID(), isFocusing = hasDecidedToFight});
            return hasDecidedToFight;
        }
    }
}
