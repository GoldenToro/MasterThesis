using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Logging;
using UnityEngine;

namespace Tester
{
    /// <summary>
    /// Collects game statistics events and compiles them into their final results.
    /// </summary>
    public class PositionAnalyzer
    {
        private readonly int bot1ID;
        private readonly int bot2ID;

        public string BotMatchId { get; set; } = "1";
        private readonly Dictionary<int, List<(Vector2 position, string botMatchId)>> positions = new();
        
        public PositionAnalyzer(int bot1ID, int bot2ID)
        {
            this.bot1ID = bot1ID;
            this.bot2ID = bot2ID;
            positions[bot1ID] = new();
            positions[bot2ID] = new();
        }

        public void Setup()
        {
            PositionInfoGameEvent.Instance.AddListener(LogPosition);
        }

        private void LogPosition(PositionInfo obj)
        {
            positions[obj.entityID].Add((new Vector2(obj.x, obj.z), BotMatchId));
        }

        public void TearDown()
        {
            PositionInfoGameEvent.Instance.RemoveListener(LogPosition);
        }

        public void Reset()
        {    
            positions[bot1ID].Clear();
            positions[bot2ID].Clear();
        }
        
        public Tuple<string,string> CompileResultsAsCSV()
        {
            var positions1 = positions[bot1ID];
            var positions2 = positions[bot2ID];
            
            return new Tuple<string, string>(GetCSV(positions1), GetCSV(positions2));
        }

        private string GetCSV(List<(Vector2 position, string botMatchId)> positions)
        {
            var csvBuilder = new StringBuilder();
            csvBuilder.AppendLine("x,z,bot_match_id");
            foreach (var sample in positions)
            {
                csvBuilder.Append(sample.position.x.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(',');
                csvBuilder.Append(sample.position.y.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(",\"").Append(sample.botMatchId.Replace("\"", "\"\"")).AppendLine("\"");
            }

            return csvBuilder.ToString();
        }
    }
}
