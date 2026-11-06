# HW9 Part 3.2: threshold sweep over the 40 labeled cases in reports/hw09/cache_cases.yaml
# usage (repo root, the 3 HW8 agents running):
#   python -m code.hw9.p3_sweep seed     empty the cache, answer the 10 seeds with the agents, store them
#   python -m code.hw9.p3_sweep sweep    look up all 40 cases at 0.75 .. 0.95, run the agents once per missed case
import argparse
import asyncio
import csv
import json
import time
import uuid
from code.hw9.p3_cases import load_cases
from code.hw9.qa_service import FACTS_SQL, FixtureQA, facts_text, fixture_codes, qlog, version_of
from code.hw9.semantic_cache import normalize
from code.kafka_service.settings import banner
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw09" / "raw"
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
SEEDS_FILE = RAW / "p3_seeds.json"
AGENT_RUNS = RAW / "p3_agent_runs.jsonl"  # one agent answer per case that missed, reused for every threshold
ROWS_FILE = RAW / "p3_sweep_rows.csv"
SUMMARY_FILE = RAW / "p3_sweep_summary.json"


async def ask_agents(qa, query):
    codes = fixture_codes(query)
    rows = qa.load_rows(FACTS_SQL, codes)
    cid = str(uuid.uuid4())
    start = time.perf_counter()
    final = await qa.agents(query + facts_text(codes, rows), cid)
    return {
        "query": query,
        "answer": str(final.get("answer", "")).strip(),
        "review_status": final.get("status"),
        "agent_ms": round((time.perf_counter() - start) * 1000, 1),
        "data_version": version_of(codes, rows),
        "fixture_codes": codes,
        "correlation_id": cid,
    }


async def seed(args):
    banner("HW9 Part 3.2 seed the cache with the 10 seed answers")
    seeds, _ = load_cases()
    qa = FixtureQA()
    print(f"Cache reset: removed {qa.cache.clear()} cached answers")
    await qa.start()
    stored = []
    try:
        for sid, query in seeds.items():
            print(f"\n{sid}: {query}", flush=True)
            run = await ask_agents(qa, query)
            vector = qa.cache.embed_fn(normalize(query))
            cid = run["correlation_id"]
            answer, version, codes = run["answer"], run["data_version"], run["fixture_codes"]
            key = qa.cache.store(query, vector, answer, version, codes, correlation_id=cid)
            qlog("SEED_STORED", run["correlation_id"], seed=sid, key=key, agent_ms=run["agent_ms"])
            print(f"answer: {run['answer']}", flush=True)
            stored.append({"seed": sid, "key": key, **run})
    finally:
        await qa.stop()
    RAW.mkdir(parents=True, exist_ok=True)
    SEEDS_FILE.write_text(json.dumps(stored, indent=2) + "\n")
    print(f"\n{len(stored)} seeds cached, {len(qa.cache.entries())} entries in Redis, saved {SEEDS_FILE.name}")
    banner("end of seeding")


def lookup_all(qa, cases, seeds, threshold):
    by_text = {normalize(q): sid for sid, q in seeds.items()}
    qa.cache.threshold = threshold
    out = []
    for c in cases:
        start = time.perf_counter()
        hit, best, _ = qa.cache.lookup(c["query"])  # embed + nearest seed, read only: nothing is stored
        lookup_ms = (time.perf_counter() - start) * 1000
        matched = by_text.get(best["query"]) if best else None
        correct = hit and c["expected"] == "hit" and matched == c["ref"]
        out.append(
            {
                "threshold": threshold,
                "case": c["id"],
                "category": c["category"],
                "expected": c["expected"],
                "ref": c["ref"],
                "nearest_seed": matched,
                "similarity": round(best["similarity"], 4) if best else 0.0,
                "hit": hit,
                "correct_hit": correct,
                "false_hit": hit and not correct,
                "lookup_ms": round(lookup_ms, 1),
            }
        )
    return out


def load_agent_runs():
    if not AGENT_RUNS.exists():
        return {}
    return {r["case"]: r for r in map(json.loads, AGENT_RUNS.read_text().splitlines()) if r}


def summarize(rows):
    table = []
    for t in THRESHOLDS:
        rs = [r for r in rows if r["threshold"] == t]
        hits = [r for r in rs if r["hit"]]
        false_hits = [r for r in rs if r["false_hit"]]
        table.append(
            {
                "threshold": t,
                "cases": len(rs),
                "hits": len(hits),
                "correct_hits": sum(r["correct_hit"] for r in rs),
                "false_hits": len(false_hits),
                "misses": len(rs) - len(hits),
                "missed_should_hit": sum(1 for r in rs if r["expected"] == "hit" and not r["hit"]),
                "hit_rate_pct": round(100 * len(hits) / len(rs), 1),
                "false_hit_rate_pct": round(100 * len(false_hits) / len(hits), 1) if hits else 0.0,
                "mean_latency_ms": round(sum(r["latency_ms"] for r in rs) / len(rs), 1),
                "false_hit_cases": [r["case"] for r in false_hits],
            }
        )
    return table


async def sweep(args):
    banner("HW9 Part 3.2 threshold sweep, 40 labeled cases")
    seeds, cases = load_cases()
    qa = FixtureQA()
    cached = {qa.cache.r.hget(k, "query") for k in qa.cache.entries()}
    if cached != {normalize(q) for q in seeds.values()}:
        raise SystemExit("The cache must hold exactly the 10 seeds. Run: python -m code.hw9.p3_sweep seed")
    qa.cache.embed_fn("warm up")
    rows = []
    for t in THRESHOLDS:  # step 1: decisions and lookup latency at every threshold, same cache each time
        rows += lookup_all(qa, cases, seeds, t)
    missed = sorted({r["case"] for r in rows if not r["hit"]})
    runs = load_agent_runs()
    todo = [c for c in cases if c["id"] in missed and c["id"] not in runs]
    print(f"Lookups done: {len(rows)} (40 cases x {len(THRESHOLDS)} thresholds)")
    print(f"Cases that miss at least once: {len(missed)}, agent answers already saved: {len(missed) - len(todo)}")
    if todo:  # step 2: what a miss really costs, one agent run per case, reused for every threshold
        await qa.start()
        try:
            for i, c in enumerate(todo, 1):
                print(f"  agents {i}/{len(todo)}  {c['id']}  {c['query']}", flush=True)
                run = {"case": c["id"], **await ask_agents(qa, c["query"])}
                with open(AGENT_RUNS, "a") as fh:
                    fh.write(json.dumps(run) + "\n")
                runs[c["id"]] = run
        finally:
            await qa.stop()
    for r in rows:  # step 3: latency of each request = lookup, plus the agents when it missed
        r["agent_ms"] = 0.0 if r["hit"] else runs[r["case"]]["agent_ms"]
        r["latency_ms"] = round(r["lookup_ms"] + r["agent_ms"], 1)
    table = summarize(rows)
    RAW.mkdir(parents=True, exist_ok=True)
    with open(ROWS_FILE, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY_FILE.write_text(json.dumps(table, indent=2) + "\n")
    first = [r for r in rows if r["threshold"] == THRESHOLDS[0]]
    print("\nNearest cached seed for every case (similarity does not depend on the threshold):")
    print("case  category           expected ref   nearest  similarity  hit at: 0.75 0.80 0.85 0.90 0.95")
    for r in first:
        marks = " ".join(
            ("H" if x["hit"] else ".") + ("!" if x["false_hit"] else " ") for x in rows if x["case"] == r["case"]
        )
        print(
            f"{r['case']}   {r['category']:<18} {r['expected']:<8} {str(r['ref']):<5} {str(r['nearest_seed']):<8}"
            f" {r['similarity']:.4f}               {marks}"
        )
    print("(H = cache hit, . = miss, ! = false hit)\n")
    print("Threshold  Hit rate        False-hit rate     Mean latency (ms)  Missed should-hit  False hits")
    for s in table:
        print(
            f"{s['threshold']:<10.2f} {s['hits']:>2}/40 = {s['hit_rate_pct']:>5.1f}%  "
            f"{s['false_hits']:>2}/{s['hits']:<2} = {s['false_hit_rate_pct']:>5.1f}%   {s['mean_latency_ms']:>12}"
            f"       {s['missed_should_hit']:>2}/20         {', '.join(s['false_hit_cases']) or '-'}"
        )
    print("\nHit rate = hits / 40. False-hit rate = wrong cached answers / hits served.")
    qlog("P3_SWEEP_DONE", thresholds=THRESHOLDS, agent_runs=len(runs))
    banner("end of threshold sweep")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "sweep"])
    args = parser.parse_args()
    asyncio.run(seed(args) if args.command == "seed" else sweep(args))
