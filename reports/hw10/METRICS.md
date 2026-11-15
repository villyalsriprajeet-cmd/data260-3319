HW10 - Metrics

Domain 7 - Community sports league fixtures. SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7. Everything ran on my MacBook Pro (8 GB RAM, macOS) with Kafka 3.9.2 (one KRaft broker), Redis Stack 7.4.0-v8, MySQL s3319_rel, the HW8 Planner, Writer and Reviewer, the HW9 semantic cache at threshold 0.95, qwen2.5:3b through Ollama at temperature 0 and seed 3319, DeepEval 4.3.4 (GEval) and Streamlit 1.67.0. The Python environment is x86_64 (torch 2.2.2, NumPy 1.26.4, pyarrow 24.0.0). Every trace_id is the HW8 correlation_id.

Part 1 - Streamlit dashboard (code/hw10/dashboard.py, port 8620)

Pages: Summary, Evaluation, Trace lookup. @st.cache_data reads the result files again only when a file changes (the file time is part of the key); @st.cache_resource keeps one Redis connection for the live cache count.

    Summary metric            All recorded requests              Last 24 hours
    Window                    2026-11-13T21:38Z to 11-14T20:10Z   2026-11-14T00:48Z to 11-15T00:48Z
    Requests                  78                                  74
    Cache hits / misses       21 / 57                             21 / 53
    Cache hit rate            26.9%                               28.4%
    Error rate                1.3% (1 failed, injected at Writer) 1.4%
    Cache miss p50 / p95      63,090.5 / 83,305.5 ms (n = 56)     64,319.0 / 83,597.9 ms (n = 52)
    Cache hit p50 / p95       186.0 / 1,240.0 ms (n = 21)         186.0 / 1,240.0 ms (n = 21)

Source of every summary metric: reports/hw10/traces/spans.jsonl, one request span per question written by code/hw10/traced_qa.py. Hit rate = hits / (hits + misses); error rate = requests with status error / all requests; latency uses successful requests only. Questions sent straight to Kafka for the Part 3 cases have no request span and are not counted. Live Redis count when the screenshots were taken: 66 cached answers in s3319:idx:qa.

Part 2 - Evaluator (code/hw10/evaluator.py)

The evaluator consumes s3319_final (group s3319_evaluator_group), joins each final answer with its plan (s3319_tasks) and draft (s3319_drafts) by correlation_id, keeps the original text, the topic, partition and offset of each input, and writes one result to reports/hw10/eval/eval_results.jsonl and to s3319_evaluations.

    Judge setting             Value
    Library and metric        DeepEval 4.3.4 GEval, rubric 1 to 5 (1 very poor, 5 excellent)
    Judge model               qwen2.5:3b through Ollama (local), temperature 0, seed 3319, num_ctx 2048
    Criteria                  Plan Quality (plan), Helpfulness (draft and final), Final-vs-Draft (difference)
    Prompt fix                the score in GEval's example JSON is replaced by a placeholder (de-anchoring)
    Bounds                    120 s per HTTP call, 150 s per metric, 460 s per evaluation

    Over 53 evaluated requests (latest result per trace, all status ok)
    Planner plan quality      3.55
    Writer draft helpfulness  3.62
    Reviewer final helpfulness 3.66
    Final minus draft         +0.04 on average
    Reviewer changed the text 8 of 53
    Final vs draft            higher 1, same 51, lower 1

Bounded runs: the malformed test finals (two test runs, 4 MALFORMED_SKIPPED lines) were skipped and the evaluator kept going; a judge URL with nothing listening and a judge that accepts the call but never answers both ended as recorded errors instead of a hang. Example FX-00412 (trace 6c7cb780): plan 1, draft 4, final 4, Reviewer returned the draft unchanged. The plan score of 1 is a judge error: its reason says a step is missing that is step 1 of the plan. FX-00305 (trace 69d86b19) scored 1, 1, 1 before the de-anchoring fix (the saved result) and 4, 4, 4 when re-scored with the fix.

Calibration probe (judge_probe.json, FX-00305 question, five outputs of known quality):

    Output                     Expected    Original GEval prompt   De-anchored prompt
    correct answer             4-5         1                       4
    wrong facts                1-2         1                       1
    off topic                  1           1                       1
    concrete plan              4-5         1                       3
    vague plan                 1-2         1                       1

Part 3 - Judge validation (reports/hw10/eval)

20 Writer drafts frozen in eval_cases.json (sha256 2c9174bb9227e330306f33c70828ca4df8ba5a81a8be369a237ab1f6a35b50ec) and 20 human helpfulness labels in human_labels.csv, both committed before judge_runs.jsonl. Human labels: 8 x 5, 5 x 4, 0 x 3, 3 x 2, 4 x 1. The judge saw the question exactly as the Writer saw it (with the MySQL facts) and the frozen draft.

    Measure (judge median of 3 runs vs human)   Value
    Spearman rank correlation                   0.143
    Mean absolute difference                    1.7
    Exact agreement                             15%
    Within 1 point                              60%
    Judge mean / human mean                     2.9 / 3.5

    Repeatability (3 runs, same inputs and settings)
    Cases whose score changed                   0 of 20
    Mean / max absolute change                  0.0 / 0.0

Raw per-case data: judge_validation.csv (human score, note, the three judge scores, median, differences, judge reason). The judge is fully repeatable but does not agree with the human ranking. It gave 1 to honest "not available" answers (C06, C08, C09; human 5, 4, 4) and 4 to answers with invented facts (C03, C19, C20; human 1). I would not use it to gate a deployment.

Part 4.1 and 4.2 - Traces (reports/hw10/traces)

Stages in order: request, cache_lookup, inbox, planner, tasks, writer, drafts, reviewer, final, evaluation. inbox, tasks, drafts and final are queue waits (time a message sat in the Kafka topic). trace_ids.json keeps the three traces below.

    Trace     trace_id                              Total       Path and result
    miss      f7d3710d-e830-470b-90af-1cbea2d800c5  82,940 ms   similarity 0.7642, all 10 stages ok
    hit       e1aba12d-90c8-4f13-bca6-0aa794b1219d  2,325 ms    similarity 1.0, cache_lookup 2,269 ms, no agents
    failed    8e8aeab3-ffd7-415f-9108-70061d11ee21  17,787 ms   writer span error (3,243 ms), sent to dead letter

    Miss trace stages (ms)   cache_lookup 375, inbox 175, planner 30,655, tasks 152, writer 7,403,
                             drafts 63, reviewer 11,416, final 96, evaluation 32,159 (sum 82,494)

The failed trace: "RuntimeError: injected fault at WRITER for the HW10 failed-trace test"; drafts, reviewer, final and evaluation were never reached and the request ended from the dead-letter topic.

Part 4.3 - Stage latency of 50 confirmed cache misses (reports/hw10/latency)

Questions: 65 candidates, 50 kept with similarity below 0.85 to every cached question (max 0.7759) and to each other (max 0.6922); "Which venue hosts fixture FX-02718?" was dropped at 0.923 to the cached FX-00412 question. Run 2026-11-14 19:13 to 20:07 UTC, all 50 logged CACHE_MISS, inbox offsets 90 to 139 with no retries, 47.2 to 87.7 s per request. End to end includes waiting for the evaluation.

    Stage               p50 (ms)    p95 (ms)    % of cache-miss end-to-end
    Cache lookup        3,213.0     7,005.5     5.6
    Planner             9,160.5     13,213.3    14.8
    Writer              9,206.0     12,820.9    14.4
    Reviewer            12,489.0    15,553.2    19.4
    Queue wait (total)  874.0       1,558.4     1.5
    Evaluation          27,619.0    35,597.7    43.4
    Other (client)      461.5       1,773.2     1.0
    End to end          64,319.0    83,202.3    100.0

    Queue waits alone   inbox 208.0 / 803.0, tasks 149.0 / 510.9, drafts 153.5 / 488.3, final 152.5 / 569.4

    Cache hits (kept separate, n = 20)   request p50 167.0 ms, p95 547.5 ms; lookup p50 163.0 ms, p95 541.5 ms

p50 and p95 use linear interpolation; % = sum of the stage over all 50 requests / sum of end to end. The dominant contributor is the evaluation (43.4%, three GEval judge calls), then the three agents together (48.6%, the Reviewer largest at 19.4%). Kafka itself costs 1.5%. I would optimize the evaluation first: take it off the request path (the user already has the answer at "final") and score a sample, then the Reviewer, which changed the text in only 8 of 53 requests. A hit is about 385 times faster than a miss at p50. The lookup takes 3.2 s on a miss but 163 ms on a hit because the embedder competes with the loaded model and agents for 8 GB of memory.
