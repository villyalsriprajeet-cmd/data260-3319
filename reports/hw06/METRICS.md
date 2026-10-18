# HW6 Metrics (Part 3: What Memory Costs)

SID4 3319, domain 7 (Community Sports League Fixtures). Model: qwen2.5:3b through Ollama, temperature 0, seed 3319, num_ctx 4096, MacBook Pro M2 8 GB.

## Setup
- One fixed conversation of 30 user messages, sent in a fresh user and session for each setting. Messages 1, 2, 5, 12, 19 and 26 plant facts, the rest are league questions.
- After message 30 the five probes in `memory_probes.yaml` are asked. Nothing from the probes is saved. The file was committed (83f7a8c) before any run.
- Short-term window = last N stored messages (user and assistant both count). Session summary every 5 user messages, top-3 episodic facts.
- Mean prompt tokens and mean latency are per chat turn over the 30 turns. Latency covers the whole turn: reply, fact extraction and any summary. Reply-only latency is listed separately. The model is warmed up before timing starts.
- One run per setting. Raw data: `raw/sweep_turns.csv` (per turn), `raw/probe_results.json` (answers and scores), `raw/sweep_summary.json`.

## Results (assignment table)
| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |
|---|---|---|---|
| SHORT_TERM_N=4 | 365.7 | 10,790 | 4.6 |
| SHORT_TERM_N=12 | 544.8 | 11,584 | 5.0 |
| SHORT_TERM_N=30 | 915.2 | 14,444 | 4.6 |
| Eviction policy (N=12 + evict_assistant) | 347.6 | 9,209 | 4.6 |

## More detail
| Setting | Prompt tokens (own tokenizer count) | Completion tokens/turn | Reply-only latency (ms) | Upkeep input tokens/turn | Upkeep output tokens/turn |
|---|---|---|---|---|---|
| N=4 | 322.7 | 35.8 | 4,905 | 380.4 | 35.8 |
| N=12 | 467.8 | 34.7 | 6,090 | 381.9 | 38.4 |
| N=30 | 781.1 | 43.9 | 9,407 | 386.9 | 33.6 |
| Eviction | 304.5 | 32.7 | 4,563 | 369.0 | 31.4 |

Upkeep means the extra model calls that run every turn (fact extraction) or every fifth turn (session and lifetime summaries). The model-reported prompt count is 13 to 17% higher than my own count because Ollama also counts the chat template tokens. Costs use the model-reported count.

## Probe scores
| Setting | P1 name/team | P2 venue | P3 rival | P4 reminders | P5 next game | Mean |
|---|---|---|---|---|---|---|
| N=4 | 3 | 5 | 5 | 5 | 5 | 4.6 |
| N=12 | 5 | 5 | 5 | 5 | 5 | 5.0 |
| N=30 | 3 | 5 | 5 | 5 | 5 | 4.6 |
| Eviction | 3 | 5 | 5 | 5 | 5 | 4.6 |

In the three settings that scored 4.6, the answer to P1 gave the team but not the name. The three facts retrieved for P1 were the same in all four runs (kickoff time, manages the Spartans, home venue), so "The user's name is Sri" ranked below the top 3. N=12 still gave the name, which can only have come from its session summary (its window and retrieved facts did not hold it). The gap therefore reflects what the summarizer kept, not the window size, and with five probes and one run per setting it is weak evidence.

## Eviction policy
`evict_assistant`: inside the window, the 4 newest messages stay in full, and older assistant replies are dropped while older user messages are kept.

| Compared with N=12 | Value |
|---|---|
| Prompt tokens per turn | 544.8 to 347.6 (-197.2, -36.2%) |
| Mean latency | 11,584 ms to 9,209 ms (-20.5%) |
| Probe quality | 5.0 to 4.6 (-0.4, the P1 miss) |
| Cost, 10,000 conversations | $387.62 to $311.19 (-19.7%) |

## Cost estimate: 10,000 conversations of 30 turns (300,000 turns)
Pricing: $1 per million input tokens, $5 per million output tokens. Input per turn = mean prompt tokens plus upkeep input. Output per turn = mean completion tokens plus upkeep output.

| Setting | Input tokens | Output tokens | Chat only | With memory upkeep |
|---|---|---|---|---|
| N=4 | 223.8 M | 21.5 M | $163.41 | $331.18 |
| N=12 (best) | 278.0 M | 21.9 M | $215.49 | $387.62 |
| N=30 (worst) | 390.6 M | 23.3 M | $340.41 | $506.88 |
| Eviction | 215.0 M | 19.2 M | $153.33 | $311.19 |

How the best and worst were chosen: settings are ranked by probe quality first and by cost second. N=12 is the only one that answered every probe correctly, so it is the best. N=4, N=30 and the eviction run tie at 4.6, and N=30 is the most expensive of them (2.5 times the prompt tokens of N=4, 31% more cost than N=12), so it is the worst. If cost matters more than the last 0.4 of quality, the eviction run is the best value: 20% cheaper than N=12 with one probe lower.

Memory upkeep adds roughly $158 to $172 in every setting, about half of the total, so shrinking the window does not touch it. A cheaper extractor prompt would save more than any window change.

## Notes and limits
- The first N=4 run (kept as `*_run1_before_fix`) scored 4.2. The extractor returned no facts for four of the six planted messages and session summaries were cut off at the token limit, so the Sunday 2 PM change was lost. I added three short examples to the extraction prompt (different from the test messages), made summaries stricter and longer (250 tokens), and added a warm-up call, then reran all four settings. The results above are from the second run.
- Single run per setting, five probes, a small 3B model: treat differences of one probe as noise.
- Retrieval uses the top 3 facts, so a fact can be missed when several stored facts match the question. The retrieved facts for every probe are saved in `probe_results.json`.
