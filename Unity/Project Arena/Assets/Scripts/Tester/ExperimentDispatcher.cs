using System;
using UnityEngine;
using UnityEngine.SceneManagement;
#if UNITY_EDITOR
#endif

namespace Tester
{
    /// <summary>
    /// A MonoBehaviour able to dispatch to the correct scene depending on the command line parameters.
    /// </summary>
    public class ExperimentDispatcher : MonoBehaviour
    {
        private const string EXPERIMENT_PARAM = "-experimentType=";

        private const string GENOME_TESTER_TEST_NAME = "BOT_GENOME_TESTER";
        private const string GENOME_TESTER_TEST_SCENE = "GenomeTester";

        private const string MAP_TESTER_TEST_NAME = "BOT_MAP_TESTER";
        private const string MAP_TESTER_TEST_SCENE = "MapEvaluationTester";

        private void Awake()
        {
            var args = Environment.GetCommandLineArgs();
            string experimentType = null;
            foreach (var arg in args)
                if (arg.StartsWith(EXPERIMENT_PARAM))
                    experimentType = arg.Substring(EXPERIMENT_PARAM.Length);

            if (experimentType == null)
            {
                // Debug.LogError("You must supply the type of experiment to run with " + EXPERIMENT_PARAM);
                // This doesn't work...

                QuitWithError("You must supply the type of experiment to run with " + EXPERIMENT_PARAM);
                return;
            }

            switch (experimentType)
            {
                case GENOME_TESTER_TEST_NAME:
                    SceneManager.LoadScene(GENOME_TESTER_TEST_SCENE);
                    break;

                case MAP_TESTER_TEST_NAME:
                    SceneManager.LoadScene(MAP_TESTER_TEST_SCENE);
                    break;

                default:
                    QuitWithError(
                        "Unknown experiment type " + experimentType + "\n" +
                        "Known experiments are:\n" +
                        // ROCKET_SUICIDE_TEST_NAME + ",\n"
                        GENOME_TESTER_TEST_NAME + ",\n" +
                        MAP_TESTER_TEST_NAME + ",\n"
                    );
                    return;
            }
        }

        private static void QuitWithError(string errorMessage)
        {
            // TODO Understand how to quit batchmode
            Application.Quit(-1);
        }
    }
}