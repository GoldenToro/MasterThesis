Pilot configurations: 87 experiments, 29 variants/references x 3 seeds.
All JSON files here are runnable experiments; the manifest is ../../pilot/pilot_plan.json.
Use the bounded pilot launcher for the overnight run, especially for paid LLM methods.
Paid configurations share pilot/llm_budget.json with a $5.50 reservation cap and at most 36 requests, including corrections.
Use pilot/run_pilot.py for the eight-hour cutoff, fresh pilot Unity build and cumulative reports.
These small runs screen parameters and system correctness; they do not establish optimal thesis settings.
Manual maps are validation references of different sizes, not comparable generator baselines.
No credentials are embedded; Grok reads XAI_API_KEY from the launcher environment.
