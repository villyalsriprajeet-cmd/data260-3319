HW9 - Metrics

Domain 7 - Community sports league fixtures. SID4 3319, PORT_BASE 8619, PREFIX s3319, SEED 3319, VERIFY_SEED 263319, DOMAIN_ID 7. Everything ran on my MacBook Pro (Apple M2, 8 GB RAM, macOS) with Redis Stack 7.4.0-v8 (Redis 7.4.7 with vector search) in Docker, MySQL s3319_rel, Kafka 3.9.2, qwen2.5:3b through Ollama at temperature 0, and all-MiniLM-L6-v2 (384 dims) for embeddings. Every Redis key starts with s3319:.

Part 1 - View counter (Redis INCR, MySQL sync every 10 views)

    Check                                   Result
    25 accesses to fixture 42 (FX-00042)    Access #1 .. #25, totals 1 .. 25
    MySQL syncs                             2, right after #10 and #20 ("Synced views to database")
    Final values                            Redis s3319:views:fixture:42 = 25, MySQL fixtures.views = 20
    updated_at after the syncs              unchanged (sync sets updated_at = updated_at)
    Average time per access                 2.74 ms (first sync 14.3 ms opened the connection, second 2.5 ms)

Part 2 - Semantic cache in front of the HW8 agents (threshold 0.85)

12 queries: 5 new, 3 exact duplicates, 4 paraphrases. Final run with per-step timing.

    Measure                                  Value
    Cache hit rate                           7/12 = 58.3% (all duplicates and paraphrases hit, all new questions missed)
    Similarity of hits                       duplicates 1.0, paraphrases 0.956 to 0.983
    Highest similarity of a new question     0.7185
    Average latency, cached                  2,410.6 ms
    Average latency, non-cached              30,935.6 ms
    Inside every lookup                      embed 1,946.7 ms + vector search 136.2 ms
    Inside every miss                        agents 28,997.5 ms (Planner, Writer, Reviewer over Kafka)
    Embedding alone, machine idle            median 17.2 ms (mean 28.4 ms, 20 questions)

A hit was about 13x faster than a miss in this run. The cached latency is high because the embedding ran on the CPU (PyTorch under Rosetta, x86_64) while Ollama, three agents, Kafka, Redis and MySQL shared 8 GB; with the machine idle the same embedding took about 17 ms.

Part 3 - Threshold sweep, cost model, stale answers

Labels: reports/hw09/cache_cases.yaml, 10 seeds and 40 cases (10 exact duplicates, 10 paraphrases, 10 superficially similar, 10 unrelated), committed in 4473d65 before the sweep (ecbeef3). No labels were changed.

    Threshold  Hit rate        False-hit rate   Mean latency (ms)  Misses  False hits  Total cost
    0.75       28/40 = 70.0%   9/28 = 32.1%     7,535.4            12      9           192
    0.80       27/40 = 67.5%   9/27 = 33.3%     7,995.7            13      9           193
    0.85       24/40 = 60.0%   7/24 = 29.2%     9,446.0            16      7           156
    0.90       19/40 = 47.5%   5/19 = 26.3%     11,978.3           21      5           121
    0.95       17/40 = 42.5%   4/17 = 23.5%     13,220.6           23      4           103  <- shipped

Hit rate = hits / 40. False-hit rate = wrong cached answers / hits served. Mean latency = lookup, plus the measured agent time (about 23 s) when the case missed. Total cost = misses x 1 + false hits x 20.

Cost model: a miss costs 1 unit (one Planner, Writer and Reviewer run, three qwen2.5:3b calls, about 23 s while the user waits). A false hit costs 20 units (a wrong ticket count, venue or team for a real fixture; the fan or manager acts on it and a league volunteer spends 5 to 10 minutes fixing it). 0.95 is the cheapest whenever a false hit costs at least 5 misses.

False hit shown in full: D01 "How many tickets are still available for fixture FX-00043?" matched S01 (FX-00042) at 0.9896 and returned "51 tickets ... Milpitas Field" instead of "88 tickets ... San Mateo Arena". The two questions differ in 1 of 13 word pieces (##42 vs ##43). Code-only look-alikes (D01, D02, D05, D06, 0.98 to 0.996) stay false hits at every threshold.

Stale answer and invalidation (S01, FX-00042):

    Step                                      Result
    Before the update                         MySQL 51 tickets, cache hit returns 51
    UPDATE tickets_available = 12             updated_at 2026-10-01T17:14:36 -> 2026-11-05T16:06:01
    Version check off                         stale hit, still 51 (marker differs from MySQL)
    Version check on                          STALE_INVALIDATED, agents rerun (29.7 s), answer 12, new marker stored
    Next request                              fresh hit, 12
    Cost of the check on every hit            mean 0.94 ms, median 0.48 ms, max 9.46 ms (50 runs)

Part 4 - Answering Agent and Evaluator Agent

Reference: reports/hw09/part4/reference_fixtures.json, 42 fixtures from s3319_rel plus 3 codes that do not exist. Questions only: training 16, validation 12, test 16. At most 2 attempts.

Training (v2 questions, specific feedback): first attempt 14/16, final 16/16. wrong_difference failed in TR08 and TR12, so lesson_001 was created after TR12; TR16 loaded lesson_001 and passed on the first attempt.

Validation (first attempt only): no lessons 9/12, with lesson_001 9/12. Failures 3 -> 3, nothing broke, unrelated questions (VA11, VA12) still answered "not available", so lesson_001 was kept.

    Variant                Correct  Incorrect  Avg attempts  Avg latency (s)
    Baseline               14/16    2          1.00          3.82
    Evaluator Repair       15/16    1          1.12          3.08
    Lesson Memory          16/16    0          1.12          3.13
    Validated Improvement  16/16    0          1.12          3.18

Still wrong: Baseline TE07 (guessed a referee) and TE10 (said "376 more", the truth is 296 fewer); Evaluator Repair TE10 (fixed the direction but kept 376). With lesson_001 loaded, TE10 was revised to "296 fewer" and passed. Lesson Memory and Validated Improvement are the same here because validation kept the only lesson. Baseline latency is a little higher because it ran first and paid for loading the model.

Development history (training data only, before validation and test were ever run): v1 questions were too easy (15/16 first attempt, no repeated failure, no lessons) and exposed two evaluator bugs (TR04 correct answer graded wrong, TR16 wrong direction graded correct); a third bug (fixture codes sorted, so A - B could flip) was found while fixing them. All three were fixed and the questions were made harder (totals, signed differences, matchweek gaps, three-part questions). Generic feedback did not fix TR08 and TR12 (the model repeated the same answer at temperature 0), so the feedback was made to name the exact mistake without giving the value.
