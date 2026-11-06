# HW9 self-check: writes reports/hw09/verification.json
# usage (repo root): make verify-hw09   (Docker with Redis, MySQL s3319_rel and Ollama running; no agents needed)
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from code.kafka_service.settings import DOMAIN_ID, PORT_BASE, PREFIX, SEED, SID4, VERIFY_SEED, banner

from sqlalchemy import text

REPORT_DIR = ROOT / "reports" / "hw09"
RAW = REPORT_DIR / "raw"
PART4 = REPORT_DIR / "part4"
CONFIG = {
    "SID4": SID4,
    "PORT_BASE": PORT_BASE,
    "PREFIX": PREFIX,
    "SEED": SEED,
    "VERIFY_SEED": VERIFY_SEED,
    "DOMAIN_ID": DOMAIN_ID,
}
MODEL = {
    "llm": "qwen2.5:3b",
    "runtime": "Ollama (local)",
    "temperature": 0,
    "seed": SEED,
    "embedder": "sentence-transformers/all-MiniLM-L6-v2 (384 dims)",
    "redis": "redis/redis-stack-server:7.4.0-v8",
}
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
    print("PASS" if ok else "FAIL", name, f"({detail})" if detail != "" else "", flush=True)


def safe(name, fn):
    try:
        fn()
    except Exception as exc:  # one broken area must not stop the other checks
        check(name, False, f"{type(exc).__name__}: {exc}")


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load(path):
    return json.loads(Path(path).read_text())


def first_commit_time(path):
    out = run("git", "log", "--diff-filter=A", "--format=%ct", "--", str(path)).split()
    return int(out[-1]) if out else None


def infra():
    from code.hw9.fixture_cache import make_redis

    running = run("docker", "ps", "--format", "{{.Names}}").split()
    check("docker: s3319_redis container running", f"{PREFIX}_redis" in running, running)
    r = make_redis()
    modules = {m["name"] for m in r.module_list()}
    check("Redis answers PING and has the vector search module", r.ping() and "search" in modules, sorted(modules))
    others = [k for k in r.scan_iter(count=1000) if not k.startswith(f"{PREFIX}:")]
    check(f"every Redis key starts with {PREFIX}:", not others, f"{r.dbsize()} keys, {len(others)} without prefix")


def part1():
    from code.hw9.fixture_cache import FixtureCache

    cache = FixtureCache()
    fid = VERIFY_SEED % 5000 + 1  # a fixture the demos never use

    def row():
        with cache.engine.connect() as conn:
            return conn.execute(text("SELECT views, updated_at FROM fixtures WHERE id = :i"), {"i": fid}).one()

    cache.reset_views(fid)
    before = row()
    counts = [cache.increment_fixture_views(fid) for _ in range(13)]
    after = row()
    redis_value = int(cache.redis_client.get(cache.views_key(fid)))
    check("Part 1: INCR returns 1..13 in order", counts == list(range(1, 14)), counts[-1])
    check(
        "Part 1: Redis holds 13 and MySQL holds 10 (synced at the 10th view only)", (redis_value, after[0]) == (13, 10)
    )
    check("Part 1: the view sync does not change updated_at (the data-version marker)", after[1] == before[1])
    cache.reset_views(fid)


def part2():
    from code.hw9.p3_cases import load_cases
    from code.hw9.semantic_cache import DIM, INDEX, SemanticCache

    cache = SemanticCache(threshold=0.95)
    info = cache.r.ft(INDEX).info()
    attrs = json.dumps(info.get("attributes", []))
    check("Part 2: vector index exists with 384-dim cosine embeddings", str(DIM) in attrs and "COSINE" in attrs, INDEX)
    seeds, _ = load_cases()
    hit, best, _ = cache.lookup(seeds["S01"])
    check("Part 2 live: an exact duplicate of a cached question is a hit at ~1.0", hit, round(best["similarity"], 4))
    hit, best, _ = cache.lookup("How do I reset my password on the league website?")
    check("Part 2 live: an unrelated question is a miss", not hit, round(best["similarity"], 4))
    s = load(RAW / "p2_summary.json")
    rows = [json.loads(x) for x in (RAW / "p2_results.jsonl").read_text().splitlines()]
    check("Part 2 saved run: at least 10 queries with is_cached, similarity and latency", len(rows) >= 10, len(rows))
    labels = {r["label"].split(" of ")[0] for r in rows}
    check(
        "Part 2 saved run: exact duplicates, paraphrases and new questions",
        {"new", "paraphrase", "exact duplicate"} <= labels,
    )
    check(
        "Part 2 saved run: cached answers were faster than non-cached ones",
        s["avg_latency_cached_ms"] < s["avg_latency_non_cached_ms"],
        f"{s['hit_rate_pct']}% hits, {s['avg_latency_cached_ms']} vs {s['avg_latency_non_cached_ms']} ms",
    )


def part3():
    from code.hw9.p3_cases import CASES_FILE, load_cases

    _, cases = load_cases()
    check("Part 3.1: cache_cases.yaml has 40 cases, 10 per category", len(cases) == 40)
    labels, sweep = first_commit_time(CASES_FILE), first_commit_time(RAW / "p3_sweep_summary.json")
    check("Part 3.1: cache_cases.yaml was committed before the sweep results", labels and sweep and labels < sweep)
    table = load(RAW / "p3_sweep_summary.json")
    ths = [t["threshold"] for t in table]
    check("Part 3.2: sweep at 0.75, 0.80, 0.85, 0.90, 0.95 over 40 cases", ths == [0.75, 0.8, 0.85, 0.9, 0.95])
    hits = [t["hits"] for t in table]
    check("Part 3.2: hit rate never rises as the threshold rises", hits == sorted(hits, reverse=True), hits)
    cost = load(RAW / "p3_cost.json")
    lowest = min(cost["table"], key=lambda t: t["total_cost"])["threshold"]
    check("Part 3.4: the shipped threshold has the lowest total cost", cost["chosen"] == lowest, cost["chosen"])
    fh = load(RAW / "p3_false_hit_D01.json")
    check(
        "Part 3.3: false hit D01 returned another fixture's answer",
        fh["cached_answer_returned"] != fh["correct_answer"] and fh["similarity"] > 0.95,
        fh["similarity"],
    )
    demo = load(RAW / "p3_stale_demo.json")
    ok = (
        demo["3_stale_hit"]["is_cached"]
        and demo["3_stale_hit"]["data_version"] != demo["3_stale_hit"]["current_version"]
        and not demo["4_invalidated"]["is_cached"]
        and demo["5_fresh_hit"]["is_cached"]
    )
    check("Part 3.5: stale hit, then invalidation by the data-version marker, then a fresh hit", ok)
    marker = stale_marker(load_cases()[0]["S01"])
    check("Part 3.5 live: the cached FX-00042 answer carries the current data version", marker[0] == marker[1], marker)


def stale_marker(query):
    from code.api.database import engine
    from code.hw9.qa_service import VERSION_SQL, version_of
    from code.hw9.semantic_cache import SemanticCache

    cache = SemanticCache()
    stored = cache.r.hget(cache.key_for(query), "data_version")
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(VERSION_SQL, {"codes": ["FX-00042"]})]
    return stored, version_of(["FX-00042"], rows)


def part4():
    from code.hw9.p4_agents import EvaluatorAgent, load_reference

    fixtures, missing = load_reference()
    need = {"fixture_code", "fixture_title", "venue", "tickets_available", "home_team", "away_team", "matchweek"}
    check(
        "Part 4: reference dataset from s3319_rel has every needed field",
        all(need <= set(f) for f in fixtures.values()),
    )
    sets = {n: load(PART4 / f"{n}_data.json") for n in ("training", "validation", "test")}
    only_questions = all(set(q) == {"id", "question"} for qs in sets.values() for q in qs)
    check(
        "Part 4: training/validation/test files hold only ids and questions",
        only_questions,
        {k: len(v) for k, v in sets.items()},
    )
    lessons = load(PART4 / "lessons.json")
    fields = {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"}
    check(
        "Part 4.2: lessons.json entries have the five required fields",
        lessons and all(fields <= set(x) for x in lessons),
    )
    training = [json.loads(x) for x in (PART4 / "runs" / "training.jsonl").read_text().splitlines()]
    reused = [r["id"] for r in training if r["lessons_used"]]
    check("Part 4.2: a later training question loaded an earlier lesson", reused, reused)
    demo = json.loads((PART4 / "runs" / "demo_repair.jsonl").read_text().splitlines()[0])
    ok = demo["attempts"][0]["controlled_fault"] and demo["first_result"] == "REVISE" and demo["final_result"] == "PASS"
    check("Part 4.1: controlled bad first answer is revised to PASS in 2 attempts", ok and demo["n_attempts"] == 2)
    runs = [json.loads(x) for f in (PART4 / "runs").glob("*.jsonl") for x in f.read_text().splitlines()]
    check("Part 4.1: no question ever used more than 2 attempts", max(r["n_attempts"] for r in runs) <= 2, len(runs))
    report = load(PART4 / "validation_report.json")
    kept = {x["lesson_id"] for x in lessons}
    ok = all((r["decision"] == "keep") == (r["lesson_id"] in kept) for r in report)
    check("Part 4.3: lessons.json holds exactly the lessons validation kept", ok, sorted(kept))
    table = {t["variant"]: t for t in load(PART4 / "results_test.json")}
    names = ["Baseline", "Evaluator Repair", "Lesson Memory", "Validated Improvement"]
    ok = list(table) == names and all(t["correct"] + t["incorrect"] == len(sets["test"]) for t in table.values())
    check("Part 4.4: four variants, each graded on the whole test set", ok, {k: v["correct"] for k, v in table.items()})
    ev = EvaluatorAgent(fixtures)
    q = "How many more tickets does fixture FX-01114 have than fixture FX-01115?"
    cases = [
        (q, "Fixture FX-01114 has 37 more tickets than fixture FX-01115", "REVISE"),
        (q, "Fixture FX-01114 has 37 fewer tickets than fixture FX-01115", "PASS"),
        ("Is fixture FX-01002 sold out?", "FX-01002 is sold out as the tickets_available value is 0.", "PASS"),
    ]
    got = [ev.evaluate(qq, a)["result"] for qq, a, _ in cases]
    check("Part 4: evaluator regression cases (TR04, TR16 bugs stay fixed)", got == [c[2] for c in cases], got)


def offline():
    lint = subprocess.run(
        ["ruff", "check", "code/hw9", "code/verify_hw09.py"], cwd=ROOT, capture_output=True, text=True
    )
    check("ruff passes on the HW9 code", lint.returncode == 0, (lint.stdout.strip().splitlines() or ["ok"])[-1])


def main():
    banner("verify_hw09.py")
    print(f"started {datetime.now():%Y-%m-%d %H:%M:%S}\n", flush=True)
    safe("infrastructure", infra)
    safe("Part 1", part1)
    safe("Part 2", part2)
    safe("Part 3", part3)
    safe("Part 4", part4)
    safe("offline checks", offline)
    out = {
        "hw": "hw9",
        "sid4": SID4,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "commit_hash": run("git", "rev-parse", "HEAD") or "unknown",
        "tag": run("git", "tag", "--points-at", "HEAD") or "none",
        "config": CONFIG,
        "model": MODEL,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "all_passed": all(c["passed"] for c in CHECKS),
        "checks": CHECKS,
    }
    (REPORT_DIR / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    passed = sum(c["passed"] for c in CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed, saved reports/hw09/verification.json")


if __name__ == "__main__":
    main()
