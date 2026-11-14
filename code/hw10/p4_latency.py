# HW10 Part 4.3: latency of 50 confirmed cache-miss requests by stage, with cache-hit latency kept separate
# usage (repo root): python -m code.hw10.p4_latency probe     (pick 50 questions that cannot hit the cache)
#                    python -m code.hw10.p4_latency run       (50 traced misses through agents and evaluator, resumable)
#                    python -m code.hw10.p4_latency hits      (the same questions again, as cache hits)
#                    python -m code.hw10.p4_latency analyze   (p50, p95 and share of end-to-end latency per stage)
import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from code.hw10.traced_qa import ROOT, TracedQA
from code.hw10.tracing import QUEUE_STAGES, read_spans
from code.kafka_service.settings import banner

import numpy as np

OUT = ROOT / "reports" / "hw10" / "latency"
QUESTIONS_FILE = OUT / "latency_questions.json"
MISSES_FILE = OUT / "latency_misses.jsonl"
HITS_FILE = OUT / "latency_hits.jsonl"
CSV_FILE = OUT / "latency_per_request.csv"
SUMMARY_FILE = OUT / "latency_summary.json"
TARGET = 50
SAFE_SIM = 0.85  # well under the 0.95 cache threshold, so every request is a miss
HIT_COUNT = 20
STAGES = ["cache_lookup", "inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final", "evaluation"]
GENERAL = [
    "How should a club organise carpools for an away fixture?",
    "What first aid supplies should be at the pitch side for a youth match?",
    "How can parents help coaches during a weekend league game?",
    "What is a fair way to split playing time among substitutes?",
    "How should a referee handle a player who receives two yellow cards?",
    "What should a team do if their kit colours clash with the opponents?",
    "How can a league attract more volunteers for match days?",
    "What snacks are good for players at half time?",
    "How do you set up cones for a pre-match passing drill?",
    "What should a captain say before the coin toss?",
    "How can a small club raise money for new goal nets?",
    "What are good ways to keep spectators away from the touchline?",
    "How should injuries be recorded after a fixture?",
    "What should be in a match day kit bag for a goalkeeper?",
    "How can coaches keep young players motivated after a heavy defeat?",
    "How should lost property be handled at a community sports ground?",
    "What can be done to reduce noise complaints from neighbours on match days?",
    "How should a league tell fans about a late venue change?",
    "What steps keep a grass pitch playable after heavy rain?",
    "How can teams make their matches easier to attend for wheelchair users?",
    "What is the best way to post fixture results on social media?",
    "How should a coach plan a light training session the day before a match?",
    "What should an assistant referee watch for in an offside decision?",
    "How can a club welcome new families to the league?",
    "What should happen if floodlights fail during an evening fixture?",
    "How should players cool down after the final whistle?",
    "Which records should a team secretary keep for each season?",
    "How can a league keep match fees affordable for low income families?",
    "What is the role of a club welfare officer?",
    "How should drinks breaks be managed in very hot weather?",
    "How do you train new referees for youth fixtures?",
    "What makes a good team talk in the dressing room?",
    "How should a league resolve a dispute over a disallowed goal?",
    "What equipment does a groundskeeper need for line marking?",
    "How can teams reduce plastic waste at match venues?",
    "What is a sensible policy on mobile phones in the dugout?",
    "How should a trophy presentation be organised at the end of the season?",
    "What can players eat the night before a big game?",
    "How can a coach spot signs of concussion during play?",
    "What information belongs in a weekly club newsletter?",
    "How should team sheets be submitted to the referee?",
    "How can a league schedule fixtures around school holidays?",
    "What should a goalkeeper practise before kickoff?",
    "How do you organise a penalty shootout fairly?",
    "What are good ice breaker games for a new under nines squad?",
    "How should a club handle abusive comments from a parent?",
    "What should a team pack for a long bus trip to an away game?",
    "How do you choose a team captain for the season?",
    "How can grandparents get involved in supporting the club?",
    "What signage helps visitors find the right pitch at a large park?",
    "How should coaches rotate goalkeepers in youth leagues?",
    "What paperwork does a new club need to join the league?",
    "How can a team improve communication between defenders?",
    "What is a good way to thank the volunteer of the season?",
    "How should a club store balls and bibs between matches?",
    "What should a referee carry in their pocket during a match?",
    "How do you teach young players to take throw-ins correctly?",
    "What makes a good club badge design?",
    "How should a coach respond to a player arriving late?",
    "How can a league collect feedback from players after the season?",
]
FIXTURE = [
    "Which venue hosts fixture FX-02718?",
    "Is there room for a school group of 30 at fixture FX-01999?",
    "Who is the home side in fixture FX-04321?",
    "Give me the matchup title for fixture FX-00666.",
    "How busy will fixture FX-03550 be based on tickets left?",
]


def candidates():
    out = list(GENERAL)
    for i, q in enumerate(FIXTURE):
        out.insert(5 + i * 10, q)  # spread the fixture lookups through the list
    return out


def cosine(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def probe(cache=None):
    qa = TracedQA(cache=cache, engine=object())
    picked, rows = [], []
    for q in candidates():
        vec = qa.cache.embed_fn(q)
        _, best, _ = qa.cache.lookup(q, vec)
        cache_sim = round(best["similarity"], 4) if best else 0.0
        pair_sim, pair_q = 0.0, None
        for p in picked:
            s = cosine(vec, p["vec"])
            if s > pair_sim:
                pair_sim, pair_q = s, p["question"]
        keep = len(picked) < TARGET and cache_sim < SAFE_SIM and pair_sim < SAFE_SIM
        rows.append({"question": q, "cache_sim": cache_sim, "pair_sim": round(pair_sim, 4), "kept": keep})
        status = "kept" if keep else ("spare" if len(picked) >= TARGET else "drop")
        near = pair_q if pair_sim >= cache_sim else (best or {}).get("query")
        note = f"  (too close to: {near})" if status == "drop" else ""
        print(f"  cache {cache_sim:.3f}  pair {pair_sim:.3f}  {status:<5} {q}{note}", flush=True)
        if keep:
            picked.append({"question": q, "vec": vec})
    if len(picked) < TARGET:
        sys.exit(f"only {len(picked)} safe questions, need {TARGET}; nothing saved")
    OUT.mkdir(parents=True, exist_ok=True)
    kept = [r for r in rows if r["kept"]]
    info = {"safe_similarity": SAFE_SIM, "cache_threshold": qa.cache.threshold, "candidates": rows}
    info.update(questions=[r["question"] for r in kept], max_cache_sim=max(r["cache_sim"] for r in kept))
    info["max_pair_sim"] = max(r["pair_sim"] for r in kept)
    QUESTIONS_FILE.write_text(json.dumps(info, indent=2) + "\n")
    print(
        f"\nkept {len(kept)} of {len(rows)}; max similarity to the cache {info['max_cache_sim']}, "
        f"to each other {info['max_pair_sim']}, all below {SAFE_SIM}; saved {QUESTIONS_FILE.relative_to(ROOT)}"
    )


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


async def run_misses(qa=None):
    questions = json.loads(QUESTIONS_FILE.read_text())["questions"]
    done = {r["question"] for r in load_jsonl(MISSES_FILE) if r["status"] == "ok" and r["path"] == "miss"}
    todo = [q for q in questions if q not in done]
    print(f"{len(done)} of {len(questions)} already measured, {len(todo)} to go", flush=True)
    qa = qa or TracedQA()
    await qa.start()
    t_start = time.monotonic()
    try:
        for n, q in enumerate(todo, 1):
            r = await qa.ask(q, wait_eval=True, timeout=900)
            row = {"question": q, "trace_id": r["trace_id"], "path": r["path"], "status": r["request"]["status"]}
            row.update(error=r["request"]["error"], e2e_ms=r["request"]["duration_ms"])
            row["lookup_similarity"] = r["lookup"]["similarity"]
            OUT.mkdir(parents=True, exist_ok=True)
            with open(MISSES_FILE, "a") as fh:
                fh.write(json.dumps(row) + "\n")  # saved after every request, so a rerun resumes
            eta = (time.monotonic() - t_start) / n * (len(todo) - n) / 60
            mark = "ok" if row["status"] == "ok" and row["path"] == "miss" else "NOT COUNTED"
            print(
                f"[{len(done) + n:2d}/{len(questions)}] {mark:<11} {row['e2e_ms'] / 1000:6.1f} s  "
                f"sim {row['lookup_similarity']}  about {eta:4.0f} min left  {q}",
                flush=True,
            )
    finally:
        await qa.stop()


async def run_hits(qa=None):
    misses = [r for r in load_jsonl(MISSES_FILE) if r["status"] == "ok" and r["path"] == "miss"]
    qa = qa or TracedQA()
    await qa.start()
    try:
        for r in misses[:HIT_COUNT]:
            h = await qa.ask(r["question"], wait_eval=False, timeout=60)
            row = {"question": r["question"], "trace_id": h["trace_id"], "path": h["path"]}
            row.update(status=h["request"]["status"], e2e_ms=h["request"]["duration_ms"])
            row["lookup_similarity"] = h["lookup"]["similarity"]
            with open(HITS_FILE, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(f"  {row['path']:<4} {row['e2e_ms']:8.1f} ms  sim {row['lookup_similarity']}  {r['question']}")
    finally:
        await qa.stop()


def pct(values, q):
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[q - 1], 1)  # linear interpolation


def stats(values, total=None):
    out = {"n": len(values), "p50_ms": round(statistics.median(values), 1), "p95_ms": pct(values, 95)}
    out["mean_ms"] = round(statistics.mean(values), 1)
    if total:
        out["share_pct"] = round(100 * sum(values) / total, 1)  # share of all end-to-end time
    return out


def analyze():
    spans = read_spans()
    misses = [r for r in load_jsonl(MISSES_FILE) if r["status"] == "ok" and r["path"] == "miss"]
    rows, skipped = [], []
    for r in misses:
        mine = {s["stage"]: s for s in spans if s["trace_id"] == r["trace_id"]}
        if not all(st in mine for st in ["request", *STAGES]):
            skipped.append(r["trace_id"])
            continue
        row = {"trace_id": r["trace_id"], "question": r["question"], "e2e": mine["request"]["duration_ms"]}
        row.update({st: mine[st]["duration_ms"] for st in STAGES})
        row["queue_wait_total"] = round(sum(row[st] for st in QUEUE_STAGES), 1)
        row["other"] = round(row["e2e"] - sum(row[st] for st in STAGES), 1)  # client work between spans
        rows.append(row)
    if len(rows) < TARGET:
        print(f"warning: only {len(rows)} complete miss traces (target {TARGET}); skipped {len(skipped)}")
    total = sum(r["e2e"] for r in rows)
    table = {st: stats([r[st] for r in rows], total) for st in [*STAGES, "queue_wait_total", "other"]}
    table["end_to_end"] = stats([r["e2e"] for r in rows], total)
    hits = [h for h in load_jsonl(HITS_FILE) if h["path"] == "hit"]
    hit_lookup = [
        s["duration_ms"]
        for s in spans
        if s["stage"] == "cache_lookup" and s["trace_id"] in {h["trace_id"] for h in hits}
    ]
    summary = {
        "miss_requests": len(rows),
        "skipped_incomplete": skipped,
        "percentile_method": "linear interpolation (statistics.quantiles, inclusive)",
        "share_method": "sum of the stage over all requests / sum of end-to-end over all requests",
        "queue_stages": QUEUE_STAGES,
        "stages": table,
        "cache_hits": {
            "request": stats([h["e2e_ms"] for h in hits]) if hits else None,
            "cache_lookup": stats(hit_lookup) if hit_lookup else None,
        },
    }
    with open(CSV_FILE, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{len(rows)} confirmed cache-miss requests (cache threshold 0.95)\n")
    print(f"{'stage':<18} {'p50 ms':>10} {'p95 ms':>10} {'% of e2e':>9}")
    for st in [*STAGES, "queue_wait_total", "other", "end_to_end"]:
        t = table[st]
        print(f"{st:<18} {t['p50_ms']:>10.1f} {t['p95_ms']:>10.1f} {t['share_pct']:>8.1f}%")
    if hits:
        h, c = summary["cache_hits"]["request"], summary["cache_hits"]["cache_lookup"]
        print(
            f"\ncache hits (separate, n={h['n']}): request p50 {h['p50_ms']} ms, p95 {h['p95_ms']} ms; "
            f"lookup p50 {c['p50_ms']} ms, p95 {c['p95_ms']} ms"
        )
    print(f"\nsaved {CSV_FILE.relative_to(ROOT)} and {SUMMARY_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["probe", "run", "hits", "analyze"])
    args = parser.parse_args()
    banner(f"HW10 Part 4.3 latency: {args.action}")
    if args.action == "probe":
        probe()
    elif args.action == "run":
        asyncio.run(run_misses())
    elif args.action == "hits":
        asyncio.run(run_hits())
    else:
        analyze()
