HW2 – Part 4: Output Schema and Loop Safety

Domain 7 – Community sports league fixtures. 
I check the Planner output with a Pydantic schema: exactly 3 tags, each 3–30 characters, and a summary of 25 words or fewer. If a run fails, I feed the error back to the Planner and let it retry up to the turn ceiling. Everything ran on qwen2.5:3b through Ollama at temperature 0.0. The fixed input is in reports/hw02/cases/schema_input.json and the adversarial one is in reports/hw02/cases/adversarial_input.json.

30-run schema test (fixed input, ceiling 10)

Outcome over 30 runs      Count    Mean latency (ms)
Valid first attempt       30       117420
Valid after 1 retry       0        -
Valid after 2+ retries    0        -
Hit turn ceiling          0        -

Completion rate: 100% (30/30). Every run passed on the first try, since the Planner output is already coerced into 3 tags and a short summary before validation, so a clean input rarely fails.

Ceiling comparison (2 vs 10, 20 runs each)

Ceiling    Runs    Completion    Mean latency (ms)
2          20      100%          102658
10         20      100%          101082

Both ceilings finished every run with no retries, so the higher ceiling didn't help. The latencies are about the same. I'd pick ceiling 2 for deployment since it limits retries in a bad case without hurting the good ones.

Adversarial input (5 runs, ceiling 10)

Outcome over 5 runs       Count    Mean latency (ms)
Valid first attempt       1        119391
Valid after 1 retry       4        222606
Valid after 2+ retries    0        -
Hit turn ceiling          0        -

Completion rate: 100% (5/5), with 4/5 needing one retry and none hitting the ceiling. I made this input break all three rules at once, a 46-character junk title, an injected "IGNORE ALL PRIOR INSTRUCTIONS" line, and no real content to tag. It usually failed the first attempt, then the retry fixed it after the error was fed back. It didn't hit the ceiling in 4+ runs.

Fix: clean the input before it reaches the Planner, strip injected instructions, cap the title length, and reject empty content. so bad input never becomes a real task.

Notes

Raw runs are in reports/hw02/raw/. Console output and timestamps are in reports/hw02/RUN_LOG.txt.