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
    public class DeathPositionAnalyzer
    {
        private readonly int bot1ID;
        private readonly int bot2ID;
        public string BotMatchId { get; set; } = "1";
        private readonly Dictionary<int, List<(Vector4 position, string botMatchId)>> deathAndKillPositions = new();
        
        public DeathPositionAnalyzer(int bot1ID, int bot2ID)
        {
            this.bot1ID = bot1ID;
            this.bot2ID = bot2ID;
            deathAndKillPositions.Add(bot1ID, new());
            deathAndKillPositions.Add(bot2ID, new());
        }

        public void Setup()
        {
            KillInfoGameEvent.Instance.AddListener(LogDeathPosition);
        }

        public void TearDown()
        {
            KillInfoGameEvent.Instance.RemoveListener(LogDeathPosition);
        }

        public void Reset()
        {    
            deathAndKillPositions.Clear();
            deathAndKillPositions.Add(bot1ID, new());
            deathAndKillPositions.Add(bot2ID, new());
        }

        private void LogDeathPosition(KillInfo receivedInfo)
        {
            if (receivedInfo.killedEntityID == receivedInfo.killerEntityID)
            {
                // Suicide!
                return;
            }

            deathAndKillPositions[receivedInfo.killedEntityID].Add(
                (new Vector4(receivedInfo.killedX, receivedInfo.killedZ, receivedInfo.killerX, receivedInfo.killerZ), BotMatchId)
                );
        }

        public Tuple<string,string> CompileResultsAsCSV()
        {
            var positions1 = deathAndKillPositions[bot1ID];
            var positions2 = deathAndKillPositions[bot2ID];
            
            return new Tuple<string, string>(GetCSV(positions1), GetCSV(positions2));
        }

        private string GetCSV(List<(Vector4 position, string botMatchId)> positions)
        {
            var csvBuilder = new StringBuilder();
            csvBuilder.AppendLine("death_x,death_z,killer_x,killer_z,bot_match_id");
            foreach (var sample in positions)
            {
                csvBuilder.Append(sample.position.x.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(',');
                csvBuilder.Append(sample.position.y.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(',');
                csvBuilder.Append(sample.position.z.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(',');
                csvBuilder.Append(sample.position.w.ToString(CultureInfo.InvariantCulture));
                csvBuilder.Append(",\"").Append(sample.botMatchId.Replace("\"", "\"\"")).AppendLine("\"");
            }

            return csvBuilder.ToString();
        }
    }
}
