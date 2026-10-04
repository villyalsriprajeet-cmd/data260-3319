# HW5 Metrics

## Part 3 - Fault injection

I used VERIFY_SEED = 263319 and ran 50 calls at each failure rate. The retry policy was 3 attempts with a 100 ms wait, then 200 ms, and a 5 s timeout on each database attempt.

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) | Attempts |
|---|---|---|---|---|
| 0% | 100% | 26.21 | 40.88 | 50 |
| 20% | 100% | 42.61 | 148.71 | 57 |
| 50% | 84% | 131.37 | 365.17 | 86 |

I ran it twice and got the same success and failure pattern both times, so the seed works. The raw data for all 150 calls is in raw/p3_fault_injection_calls.csv and the summary is in raw/p3_fault_injection_summary.json.

## Part 5 - Agent scenarios

Model: qwen2.5:3b running locally in Ollama, temperature 0.

| Scenario | max_steps | Steps | Stop reason | Tool calls | Model time (s) |
|---|---|---|---|---|---|
| 1. Search - "Find 3 fixtures for teams called Hawks." | 5 | 2 | completed | 1 | 191.0 |
| 2. Detail - "What is the venue and how many tickets are left for fixture FX-00042?" | 5 | 2 | completed | 1 | 91.6 |
| 3. Aggregate - "Which 3 cities have the most tickets available in total?" | 5 | 2 | completed | 1 | 97.7 |
| 4. Safety rule - "List 50 fixtures played at Gilroy Field." | 5 | 1 | safety_block | 1 | 56.2 |
| 5. max_steps - "Search for Hawks fixtures, then look up the full details of the first one." | 1 | 1 | max_steps | 1 | 40.7 |

The first three finished normally. The model called one tool and then answered using only what the tool returned. In scenario 4 the model asked for 50 fixtures, and my safety rule blocked it. In scenario 5 I set max_steps to 1 on purpose, so the run stopped after the first search and never got to the second lookup.

Model time is just the step latencies from the log added up. The model is slow on my laptop (MacBook Pro M2, 8 GB): each step took somewhere between 30 and 110 seconds. The full log is in raw/agent_runs.jsonl and the results are in raw/p5_scenarios.json.