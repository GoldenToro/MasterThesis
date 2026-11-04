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
    public class KillDistanceAnalyzer
    {
        private readonly int bot1ID;
        private readonly int bot2ID;
        public string BotMatchId { get; set; } = "1";
        private readonly Dictionary<int, List<(float distance, string botMatchId)>> killDistances = new();
        
        public KillDistanceAnalyzer(int bot1ID, int bot2ID)
        {
            this.bot1ID = bot1ID;
            this.bot2ID = bot2ID;
            killDistances.Add(bot1ID, new());
            killDistances.Add(bot2ID, new());
        }

        public void Setup()
        {
            KillInfoGameEvent.Instance.AddListener(LogKillDistance);
        }

        public void TearDown()
        {
            KillInfoGameEvent.Instance.RemoveListener(LogKillDistance);
        }

        public void Reset()
        {    
            killDistances.Clear();
            killDistances.Add(bot1ID, new());
            killDistances.Add(bot2ID, new());
        }

        private void LogKillDistance(KillInfo receivedInfo)
        {
            if (receivedInfo.killedEntityID == receivedInfo.killerEntityID)
            {
                // Suicide!
                return;
            }

            var distance = Mathf.Sqrt(Mathf.Pow(receivedInfo.killedX - receivedInfo.killerX, 2) +
                                      Mathf.Pow(receivedInfo.killedZ - receivedInfo.killerZ, 2)
            );
            killDistances[receivedInfo.killerEntityID].Add((distance, BotMatchId));
        }

        public Tuple<string,string> CompileResultsAsCSV()
        {
            return new Tuple<string, string>(GetCSV(killDistances[bot1ID]), GetCSV(killDistances[bot2ID]));
        }

        private string GetCSV(List<(float distance, string botMatchId)> distances)
        {
            var csvBuilder = new StringBuilder();
            csvBuilder.AppendLine("distance,bot_match_id");
            foreach (var sample in distances)
            {
                csvBuilder.Append(sample.distance.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(",\"").Append(sample.botMatchId.Replace("\"", "\"\"")).AppendLine("\"");
            }

            return csvBuilder.ToString();
        }
    }
}
