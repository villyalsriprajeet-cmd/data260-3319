# HW9 Parts 3.3 and 3.4: one false hit in full, and the cost model over the sweep results
# usage (repo root):
#   python -m code.hw9.p3_analysis false-hit --case D01        (runs the agents once if the case never missed)
#   python -m code.hw9.p3_analysis cost --miss-cost 1 --false-hit-cost 20
import argparse
import asyncio
import csv
import json
from code.hw9 import semantic_cache as sc
from code.hw9.p3_cases import load_cases
from code.hw9.p3_sweep import AGENT_RUNS, RAW, ROWS_FILE, SEEDS_FILE, SUMMARY_FILE, ask_agents, load_agent_runs
from code.hw9.qa_service import FACTS_SQL, FixtureQA, fixture_codes
from code.kafka_service.settings import banner

RATIOS = [1, 2, 5, 10, 20, 50]  # false-hit cost / miss cost, for the sensitivity check


def facts_for(qa, query):
    rows = qa.load_rows(FACTS_SQL, fixture_codes(query))
    return [{k: str(v) for k, v in r.items() if k != "updated_at"} for r in rows]


def tokens(text):
    sc.embed("warm up")  # loads the model, then use its own tokenizer
    return sc._model.tokenizer.tokenize(text)


async def false_hit(args):
    banner(f"HW9 Part 3.3 one false hit in full: {args.case}")
    seeds, cases = load_cases()
    case = next(c for c in cases if c["id"] == args.case)
    rows = [r for r in csv.DictReader(open(ROWS_FILE)) if r["case"] == args.case]
    hit_at = [r["threshold"] for r in rows if r["false_hit"] == "True"]
    if not hit_at:
        raise SystemExit(f"{args.case} was not a false hit at any threshold")
    seed_id = rows[0]["nearest_seed"]
    seed = next(s for s in json.loads(SEEDS_FILE.read_text()) if s["seed"] == seed_id)
    qa = FixtureQA()
    runs = load_agent_runs()
    if args.case not in runs:  # it hit at every threshold, so get its correct answer from the agents once
        print("This case never missed, asking the agents once for its correct answer...", flush=True)
        await qa.start()
        try:
            runs[args.case] = {"case": args.case, **await ask_agents(qa, case["query"])}
        finally:
            await qa.stop()
        with open(AGENT_RUNS, "a") as fh:
            fh.write(json.dumps(runs[args.case]) + "\n")
    cached_tokens, incoming_tokens = tokens(seed["query"]), tokens(case["query"])
    changed = [(a, b) for a, b in zip(cached_tokens, incoming_tokens) if a != b]
    out = {
        "case": args.case,
        "category": case["category"],
        "label_reason": case["why"],
        "incoming_query": case["query"],
        "cached_query": seed["query"],
        "cached_seed": seed_id,
        "similarity": float(rows[0]["similarity"]),
        "false_hit_at_thresholds": hit_at,
        "cached_answer_returned": seed["answer"],
        "correct_answer": runs[args.case]["answer"],
        "db_facts_cached_query": facts_for(qa, seed["query"]),
        "db_facts_incoming_query": facts_for(qa, case["query"]),
        "tokens_cached": cached_tokens,
        "tokens_incoming": incoming_tokens,
        "tokens_changed": changed,
    }
    (RAW / f"p3_false_hit_{args.case}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nIncoming query ({args.case}, {case['category']}): {case['query']}")
    print(f"Cached query   ({seed_id}):                 {seed['query']}")
    print(f"Cosine similarity: {out['similarity']:.4f}  ->  false hit at thresholds {', '.join(hit_at)}")
    print(f"\nCached answer returned:\n  {seed['answer']}")
    print(f"Correct answer (agents, with the {args.case} facts):\n  {out['correct_answer']}")
    print("\nGround truth from MySQL s3319_rel:")
    for label, facts in (("cached ", out["db_facts_cached_query"]), ("incoming", out["db_facts_incoming_query"])):
        for f in facts or [{"note": "no fixture code in this question"}]:
            print(f"  {label}: {f}")
    print(f"\nTokens cached   ({len(cached_tokens)}): {' '.join(cached_tokens)}")
    print(f"Tokens incoming ({len(incoming_tokens)}): {' '.join(incoming_tokens)}")
    print(f"Tokens that differ: {changed or 'different length, see above'}")
    banner("end of false hit")


def cost(args):
    banner(f"HW9 Part 3.4 cost model: miss = {args.miss_cost}, false hit = {args.false_hit_cost}")
    table = json.loads(SUMMARY_FILE.read_text())
    for s in table:
        s["total_cost"] = s["misses"] * args.miss_cost + s["false_hits"] * args.false_hit_cost
    best = min(table, key=lambda s: (s["total_cost"], -s["threshold"]))
    print("Threshold  Hit rate          False-hit rate   Mean latency (ms)  Misses  False hits  Total cost")
    for s in table:
        mark = "  <- lowest" if s is best else ""
        print(
            f"{s['threshold']:<10.2f} {s['hits']:>2}/40 = {s['hit_rate_pct']:>5.1f}%   "
            f"{s['false_hits']:>2}/{s['hits']:<2} = {s['false_hit_rate_pct']:>5.1f}%   {s['mean_latency_ms']:>12}"
            f"   {s['misses']:>6}  {s['false_hits']:>10}  {s['total_cost']:>10g}{mark}"
        )
    print(f"\nTotal cost = misses x {args.miss_cost} + false hits x {args.false_hit_cost}")
    print("\nSensitivity: cheapest threshold for other false-hit / miss cost ratios")
    sens = []
    for ratio in RATIOS:
        costs = {s["threshold"]: s["misses"] + s["false_hits"] * ratio for s in table}
        pick = min(costs, key=lambda t: (costs[t], -t))
        sens.append({"ratio": ratio, "best_threshold": pick, "costs": costs})
        detail = ", ".join(f"{t:.2f}: {c:g}" for t, c in costs.items())
        print(f"  false hit = {ratio:>2} x miss  ->  best {pick:.2f}   ({detail})")
    out = {
        "miss_cost": args.miss_cost,
        "false_hit_cost": args.false_hit_cost,
        "table": table,
        "chosen": best["threshold"],
    }
    out["sensitivity"] = sens
    (RAW / "p3_cost.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nChosen threshold to ship: {best['threshold']:.2f} (lowest total cost {best['total_cost']:g})")
    banner("end of cost model")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("false-hit")
    p.add_argument("--case", default="D01")
    p = sub.add_parser("cost")
    p.add_argument("--miss-cost", type=float, default=1)
    p.add_argument("--false-hit-cost", type=float, default=20)
    args = parser.parse_args()
    asyncio.run(false_hit(args)) if args.command == "false-hit" else cost(args)
