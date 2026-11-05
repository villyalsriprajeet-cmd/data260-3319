# HW9 Part 2 run: 12 fixture questions (new, exact duplicates, paraphrases) through the semantic cache
# usage (repo root): python -m code.hw9.p2_run --probe        (embeddings only, no agents, a few seconds)
#                    python -m code.hw9.p2_run --reset        (empty the cache, then run all 12 through the agents)
import argparse
import asyncio
import json
from code.hw9.qa_service import FixtureQA, qlog
from code.hw9.semantic_cache import DEFAULT_THRESHOLD, embed, normalize
from code.kafka_service.settings import banner
from pathlib import Path

import numpy as np

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw09" / "raw"
QUERIES = [
    ("new", "How many tickets are still available for fixture FX-00042?"),
    ("exact duplicate of Q1", "How many tickets are still available for fixture FX-00042?"),
    ("paraphrase of Q1", "How many tickets are left for fixture FX-00042?"),
    ("new", "Where is fixture FX-00117 being played?"),
    ("paraphrase of Q4", "Where will fixture FX-00117 be played?"),
    ("exact duplicate of Q4", "Where is fixture FX-00117 being played?"),
    ("new", "Which team is the home team for fixture FX-00250?"),
    ("paraphrase of Q7", "Who is the home team in fixture FX-00250?"),
    ("new", "What should a team manager do on match day before kickoff?"),
    ("exact duplicate of Q9", "What should a team manager do on match day before kickoff?"),
    ("paraphrase of Q9", "What should the team manager do before kickoff on match day?"),
    ("new", "How should a community league handle a fixture postponed because of heavy rain?"),
]


def probe(threshold):
    banner("HW9 Part 2 similarity probe (no agents)")
    cached = []  # (number, vector) of the questions that would be stored
    for i, (label, query) in enumerate(QUERIES, 1):
        vec = embed(normalize(query))
        best = max(((float(np.dot(vec, v)), n) for n, v in cached), default=(0.0, None))
        hit = best[1] is not None and best[0] >= threshold
        if not hit:
            cached.append((i, vec))
        near = f"Q{best[1]}" if best[1] else "-"
        print(f"Q{i:<2} {label:<22} best={best[0]:.4f} vs {near:<4} -> {'HIT ' if hit else 'MISS'}  {query}")


def summarize(results, threshold):
    hits = [r for r in results if r["is_cached"]]
    misses = [r for r in results if not r["is_cached"]]

    def avg(rows, key):
        return round(sum(r[key] for r in rows) / len(rows), 1) if rows else None

    return {
        "threshold": threshold,
        "queries": len(results),
        "cache_hits": len(hits),
        "cache_misses": len(misses),
        "hit_rate_pct": round(100 * len(hits) / len(results), 1),
        "avg_latency_cached_ms": avg(hits, "latency_ms"),
        "avg_latency_non_cached_ms": avg(misses, "latency_ms"),
        "avg_lookup_ms_all": avg(results, "lookup_ms"),
        "avg_embed_ms_all": avg(results, "embed_ms"),
        "avg_search_ms_all": avg(results, "search_ms"),
        "avg_agent_ms_misses": avg(misses, "agent_ms"),
    }


async def run(args):
    banner(f"HW9 Part 2 semantic cache run, threshold {args.threshold}")
    qa = FixtureQA(threshold=args.threshold)
    if args.reset:
        print(f"Cache reset: removed {qa.cache.clear()} cached answers")
    await qa.start()
    results = []
    try:
        for i, (label, query) in enumerate(QUERIES, 1):
            print(f"\n=== Q{i} ({label}) ===\n{query}", flush=True)
            res = await qa.handle_query(query)
            res.update({"n": i, "label": label})
            results.append(res)
            print(
                f"is_cached={res['is_cached']}  similarity={res['similarity']}  latency={res['latency_ms']} ms"
                f"  (embed {res['embed_ms']} ms, vector search {res['search_ms']} ms, agents {res['agent_ms']} ms)"
            )
            print(f"answer: {res['answer']}", flush=True)
    finally:
        await qa.stop()
    summary = summarize(results, args.threshold)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "p2_results.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in results))
    (RAW / "p2_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    qlog("P2_SUMMARY", **summary)
    print("\n  #  label                   cached  similarity  latency_ms")
    for r in results:
        sim = "-" if r["similarity"] is None else f"{r['similarity']:.4f}"
        print(f"{r['n']:>3}  {r['label']:<22}  {str(r['is_cached']):<6}  {sim:>10}  {r['latency_ms']:>10}")
    print(f"\nCache hit rate: {summary['cache_hits']}/{summary['queries']} = {summary['hit_rate_pct']}%")
    print(f"Average latency, cached:     {summary['avg_latency_cached_ms']} ms")
    print(f"Average latency, non-cached: {summary['avg_latency_non_cached_ms']} ms")
    print(f"Inside every lookup: embed {summary['avg_embed_ms_all']} ms", end="")
    print(f" + vector search {summary['avg_search_ms_all']} ms")
    print(f"Inside every miss:   agents {summary['avg_agent_ms_misses']} ms")
    banner("end of Part 2 run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--reset", action="store_true", help="remove every cached answer before the run")
    parser.add_argument("--probe", action="store_true", help="only print similarities, no agents")
    args = parser.parse_args()
    probe(args.threshold) if args.probe else asyncio.run(run(args))
