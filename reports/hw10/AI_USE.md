# HW10 AI Use

## 1. What I used AI for and what I did myself
I used an AI assistant as a helper for this homework. I drafted the tracing module and the span hooks in the HW8
agent runtime, the traced Q&A client, the GEval judge wrapper and metrics, the evaluator service, the bounded run
tests, the Part 3 collection, labeling and judge scripts, the latency experiment, the Streamlit dashboard, the verify
script and the RUN_LOG builder. I also explained errors when a run failed. I did the setup and the runs myself: Docker
(Kafka, Redis, the API), MySQL, Ollama, the three agents and the evaluator, every traced question, the 50-request
latency run and the judge runs, all on my own laptop. I labeled the 20 Writer drafts myself: the assistant only put
each draft next to the MySQL facts for that fixture, and I chose every score. I took every screenshot, made all the
commits, and checked the numbers in METRICS.md against the terminal output and the saved files.

## 2. One AI output that was wrong
The first judge wrapper scored correct answers as 1. For FX-00305 the draft gave the right ticket count and venue
from the database, yet the plan, the draft and the final answer all got 1 out of 5. The wrapper sent DeepEval's GEval
prompt to qwen2.5:3b unchanged, and that prompt ends with an example JSON whose score is the lowest value of the
rubric. The 3B model copied the example score instead of using its own reason.

## 3. How I found it
The reasons the judge wrote described the answers as correct while the score was 1, so the score did not follow from
the reason. We then ran a calibration probe (reports/hw10/eval/judge_probe.json): two good and three bad outputs for
the same question, scored once with the original prompt and once with the example score removed. With the original
prompt all five outputs got 1, the correct answer and the concrete plan included, so the judge could not tell good
from bad.

## 4. What I changed and why it works now
The judge wrapper now replaces the example score in the prompt with a placeholder ("integer from the rubric that fits
your reason"); everything else in GEval stays the same, and the setting is recorded with every result (deanchor true).
With the fix the probe gave the correct answer 4, the concrete plan 3 and the three bad outputs 1, and FX-00305 was
re-scored 4, 4, 4. I kept the fixed judge for every later run and did not tune it further on the Part 3 cases, so the
validation result (Spearman 0.143) is an honest measure of this judge. Other mistakes we fixed on the way: a stdout
redirect that hid all printed output, overlapping queue and work spans, and a pyarrow version that needed NumPy 2;
each fix was re-run and checked.
