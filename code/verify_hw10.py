# HW10 self-check: writes reports/hw10/verification.json
# usage (repo root): make verify-hw10   (Docker with Kafka and Redis running; agents and Ollama not needed)
import asyncio
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from code.kafka_service.settings import DOMAIN_ID, PORT_BASE, PREFIX, SEED, SID4, VERIFY_SEED, banner

REPORT_DIR = ROOT / "reports" / "hw10"
EVAL = REPORT_DIR / "eval"
TRACES = REPORT_DIR / "traces"
LATENCY = REPORT_DIR / "latency"
AGENTS_LOG = ROOT / "reports" / "hw08" / "logs" / "agents.log"
DASHBOARD = ROOT / "code" / "hw10" / "dashboard.py"
TOLERANCE_MS = 5  # clock rounding between two spans written by different processes
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
    "judge": "DeepEval 4.3.4 GEval, 1 to 5 rubric, qwen2.5:3b through Ollama (local)",
    "embedder": "sentence-transformers/all-MiniLM-L6-v2 (384 dims)",
    "redis": "redis/redis-stack-server:7.4.0-v8",
    "dashboard": "streamlit 1.67.0",
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


def load_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def commit_times(path):
    out = run("git", "log", "--format=%ct", "--", str(path)).split()
    return [int(t) for t in out]  # newest first


def latest_by_trace(rows):
    return list({r["trace_id"]: r for r in rows}.values())  # a later rescore replaces the earlier one


def infra():
    from code.hw9.check_setup import kafka_topics
    from code.hw9.fixture_cache import make_redis

    running = run("docker", "ps", "--format", "{{.Names}}").split()
    need = {f"{PREFIX}_kafka", f"{PREFIX}_redis"}
    check("docker: s3319_kafka and s3319_redis running", need <= set(running), running)
    topics = set(asyncio.run(kafka_topics()))
    want = {f"{PREFIX}_{t}" for t in ("inbox", "tasks", "drafts", "final", "dead_letter", "evaluations")}
    check("Kafka: agent topics plus s3319_evaluations exist", want <= topics, sorted(want - topics) or "all six")
    r = make_redis()
    others = [k for k in r.scan_iter(count=1000) if not k.startswith(f"{PREFIX}:")]
    check(f"Redis answers PING and every key starts with {PREFIX}:", r.ping() and not others, f"{r.dbsize()} keys")


def render(title, trace_id=None):
    from streamlit.logger import set_log_level
    from streamlit.testing.v1 import AppTest

    set_log_level("error")  # hide the bare-mode warnings of the page test
    src = DASHBOARD.read_text()
    src = src.replace("ROOT = Path(__file__).resolve().parents[2]", f"ROOT = Path({str(ROOT)!r})")
    src = src.replace('title="Summary", default=True', 'title="Summary"')
    src = src.replace(f'title="{title}")', f'title="{title}", default=True)')  # open this page first
    at = AppTest.from_string(src, default_timeout=180).run()
    if trace_id:
        at.text_input[0].input(trace_id).run()
    return at


def part1():
    src = DASHBOARD.read_text()
    pages = [t for t in ("Summary", "Evaluation", "Trace lookup") if f'title="{t}"' in src]
    check("Part 1: dashboard has Summary, Evaluation and Trace lookup pages", len(pages) == 3, pages)
    cached = "@st.cache_data" in src and "@st.cache_resource" in src
    check("Part 1.1: dashboard uses @st.cache_data (files) and @st.cache_resource (Redis client)", cached)
    at = render("Summary")
    labels = {m.label: m.value for m in at.metric}
    need = ["Requests", "Cache hits", "Cache misses", "Cache hit rate", "Error rate", "Cache miss p50", "Cache hit p50"]
    captions = " ".join(c.value for c in at.caption)
    ok = not at.exception and all(n in labels for n in need) and "Data source" in captions and "Window" in captions
    check(
        "Part 1.1 live: Summary page renders counts, hit rate, error rate and latency with source and window",
        ok,
        {n: labels.get(n) for n in need[:5]},
    )
    at = render("Evaluation")
    labels = {m.label: m.value for m in at.metric}
    need = ["Planner: plan quality", "Spearman (median of runs)", "Mean absolute difference", "Max change"]
    check(
        "Part 1.2 live: Evaluation page renders stage scores, Spearman, mean absolute difference and repeatability",
        not at.exception and all(n in labels for n in need),
        {n: labels.get(n) for n in need},
    )
    ids = load(TRACES / "trace_ids.json")
    banners = {}
    for label, kind in (("hit", "success"), ("miss", "info"), ("failed", "error")):
        at = render("Trace lookup", ids[label]["trace_id"])
        banners[label] = " ".join(e.value for e in getattr(at, kind))[:40] if not at.exception else "exception"
    ok = banners["hit"].startswith("CACHE HIT") and banners["miss"].startswith("CACHE MISS")
    check(
        "Part 1.3 live: Trace lookup tells hit, miss and failed paths apart",
        ok and "FAILED" in banners["failed"],
        banners,
    )


def part2():
    from code.hw10.bound_test import silent_judge
    from code.hw10.geval_metrics import score
    from code.hw10.judge import LocalJudge

    rows = latest_by_trace(load_jsonl(EVAL / "eval_results.jsonl"))
    ok = [r for r in rows if r["status"] == "ok"]
    check("Part 2: evaluations saved for end-to-end questions", ok, f"{len(ok)} ok of {len(rows)} traces")
    keys = ("plan_quality", "writer_helpfulness", "final_helpfulness")
    scale = all(1 <= r[k]["score"] <= 5 and r[k]["reason"] for r in ok for k in keys)
    check("Part 2.2: plan, draft and final scores are on the 1 to 5 scale with a reason", scale)
    fields = all(
        r["writer_helpfulness"]["trace_id"] == r["trace_id"] == r["correlation_id"]
        and r["final_helpfulness"]["final_answer"]
        and {"draft_score", "final_score", "difference", "interpretation"} <= set(r["final_vs_draft"])
        for r in ok
    )
    check("Part 2.2: trace_id, final answer, both scores, difference and interpretation saved", fields)
    linked = all(
        all(r["inputs"].get(f) for f in ("question", "plan", "draft", "final_answer"))
        and all(r["source"].get(t) for t in ("tasks", "drafts"))
        and r["judge"].get("judge_model")
        for r in ok
    )
    check("Part 2.1: plan, draft and final joined by correlation_id with source offsets and judge kept", linked)
    lat_ids = {m["trace_id"] for m in load_jsonl(LATENCY / "latency_misses.jsonl") if m["status"] == "ok"}
    scored = {r["trace_id"] for r in ok}
    check("Part 2: every latency request was evaluated end to end", lat_ids <= scored, f"{len(lat_ids & scored)}")
    lines = AGENTS_LOG.read_text().splitlines()
    bad = [i for i, x in enumerate(lines) if "[EVALUATOR] MALFORMED_SKIPPED" in x]
    after = bad and any("[EVALUATOR] EVALUATED" in x for x in lines[bad[-1] :])
    check("Part 2.1 saved run: malformed finals skipped and the evaluator kept scoring", after, f"{len(bad)} skipped")
    t0 = time.perf_counter()
    res = asyncio.run(score("helpfulness", "q", "an answer", LocalJudge(base_url="http://127.0.0.1:9"), timeout=30))
    took = time.perf_counter() - t0
    check(
        "Part 2.1 live: judge unavailable is recorded as an error, no hang", res["status"] == "error", f"{took:.1f} s"
    )
    t0 = time.perf_counter()
    hang = LocalJudge(base_url=silent_judge(), timeout=3)
    res = asyncio.run(score("helpfulness", "q", "an answer", hang, timeout=10))
    took = time.perf_counter() - t0
    check(
        "Part 2.1 live: a judge that never answers is cut off", res["status"] == "error" and took < 15, f"{took:.1f} s"
    )


def part3():
    from code.hw10.p3_judge import mad, spearman

    data = load(EVAL / "eval_cases.json")
    digest = hashlib.sha256(json.dumps(data["cases"], sort_keys=True).encode()).hexdigest()
    check("Part 3.1: eval_cases.json holds 20 Writer drafts and matches its sha256", data["count"] == 20, digest[:12])
    check("Part 3.1: frozen drafts unchanged", digest == data["sha256"] and len(data["cases"]) == 20)
    with open(EVAL / "human_labels.csv") as fh:
        labels = list(csv.DictReader(fh))
    ok = len(labels) == 20 and all(1 <= int(x["human_score"]) <= 5 for x in labels)
    check("Part 3.1: human_labels.csv has one 1 to 5 label per draft", ok, len(labels))
    runs_first = min(commit_times(EVAL / "judge_runs.jsonl") or [0])
    cases_last = max(commit_times(EVAL / "eval_cases.json") or [10**12])
    labels_last = max(commit_times(EVAL / "human_labels.csv") or [10**12])
    check(
        "Part 3.1: cases and labels committed (last change) before the judge scores were added",
        runs_first and cases_last < runs_first and labels_last < runs_first,
    )
    runs = [r for r in load_jsonl(EVAL / "judge_runs.jsonl") if r["status"] == "ok"]
    per_run = {n: len({r["case_id"] for r in runs if r["run"] == n}) for n in (1, 2, 3)}
    same = all(r["cases_sha256"] == digest for r in runs)
    check(
        "Part 3.3: three judge runs over the same 20 frozen drafts", per_run == {1: 20, 2: 20, 3: 20} and same, per_run
    )
    summary = load(EVAL / "judge_validation.json")
    with open(EVAL / "judge_validation.csv") as fh:
        rows = list(csv.DictReader(fh))
    human = [int(r["human_score"]) for r in rows]
    median = [float(r["judge_median"]) for r in rows]
    again = {"spearman": spearman(human, median), "mean_abs_diff": mad(human, median)}
    saved = {k: summary["agreement_median"][k] for k in again}
    check("Part 3.2: Spearman and mean absolute difference recompute from the raw per-case CSV", again == saved, saved)
    changes = [float(r["run_change"]) for r in rows]
    rep = summary["repeatability"]
    ok = rep["cases_with_any_change"] == sum(c > 0 for c in changes) and rep["max_change"] == max(changes)
    check("Part 3.3: repeatability (cases changed, max change) recomputes from the CSV", ok, rep)


def part4():
    from code.hw10.p4_latency import STAGES, pct
    from code.hw10.tracing import QUEUE_STAGES, STAGE_ORDER, read_spans, to_dt

    spans = read_spans()
    need = {"trace_id", "stage", "start", "end", "status"}
    ok = all(need <= set(s) and (s["status"] == "ok" or s["error"]) for s in spans)
    check("Part 4.1: every span has trace_id, stage, start, end, status (and error when failed)", ok, len(spans))
    by = {}
    for s in spans:
        by.setdefault(s["trace_id"], {})[s["stage"]] = s
    ids = load(TRACES / "trace_ids.json")
    check("Part 4.2: hit, miss and failed trace ids saved for the dashboard", {"hit", "miss", "failed"} <= set(ids))
    miss = by[ids["miss"]["trace_id"]]
    order = STAGE_ORDER[1:]  # cache_lookup to evaluation
    tiled = all(to_dt(miss[b]["start"]) >= to_dt(miss[a]["end"]) - _ms(TOLERANCE_MS) for a, b in zip(order, order[1:]))
    check(
        "Part 4.2: miss trace runs cache_lookup, inbox, tasks, drafts, final and evaluation in order",
        set(STAGE_ORDER) <= set(miss) and tiled,
        f"{miss['request']['duration_ms']} ms",
    )
    hit = by[ids["hit"]["trace_id"]]
    look = hit["cache_lookup"]["attrs"]
    check(
        "Part 4.2: hit trace is a cache_lookup hit with no agent stages",
        look["result"] == "hit" and set(hit) <= {"request", "cache_lookup"},
        f"similarity {look['similarity']}",
    )
    bad = by[ids["failed"]["trace_id"]]
    stage = bad["request"]["attrs"].get("failing_stage")
    ok = bad["request"]["status"] == "error" and bad.get(stage, {}).get("status") == "error"
    check(
        "Part 4.2: failed trace names the failing stage and its error",
        ok,
        f"{stage}: {bad.get(stage, {}).get('error')}",
    )
    misses = [m for m in load_jsonl(LATENCY / "latency_misses.jsonl") if m["status"] == "ok" and m["path"] == "miss"]
    looked = [by[m["trace_id"]]["cache_lookup"]["attrs"] for m in misses]
    ok = len({m["question"] for m in misses}) >= 50 and all(
        a["result"] == "miss" and a["similarity"] < 0.95 for a in looked
    )
    check(
        "Part 4.3: at least 50 confirmed cache misses",
        ok,
        f"{len(misses)}, max similarity {max(a['similarity'] for a in looked)}",
    )
    summary = load(LATENCY / "latency_summary.json")
    rows = [by[m["trace_id"]] for m in misses if all(st in by[m["trace_id"]] for st in ["request", *STAGES])]
    worst = 0.0
    for st in STAGES:
        vals = [r[st]["duration_ms"] for r in rows]
        saved = summary["stages"][st]
        worst = max(
            worst, abs(pct(vals, 95) - saved["p95_ms"]), abs(round(statistics.median(vals), 1) - saved["p50_ms"])
        )
    queue = [round(sum(r[q]["duration_ms"] for q in QUEUE_STAGES), 1) for r in rows]
    worst = max(worst, abs(pct(queue, 95) - summary["stages"]["queue_wait_total"]["p95_ms"]))
    check(
        "Part 4.3: p50 and p95 per stage and total queue wait recompute from the spans",
        worst <= 0.1,
        f"max gap {worst}",
    )
    shares = sum(summary["stages"][st]["share_pct"] for st in [*STAGES, "other"])
    check("Part 4.3: stage shares of end-to-end latency add up to 100%", abs(shares - 100) <= 0.5, round(shares, 1))
    hits = [h for h in load_jsonl(LATENCY / "latency_hits.jsonl") if h["path"] == "hit"]
    ch = summary["cache_hits"]["request"]
    check("Part 4.3: cache-hit latency kept separate from the misses", len(hits) >= 20 and ch["n"] == len(hits), ch)


def _ms(n):
    from datetime import timedelta

    return timedelta(milliseconds=n)


def offline():
    lint = subprocess.run(
        ["ruff", "check", "code/hw10", "code/verify_hw10.py"], cwd=ROOT, capture_output=True, text=True
    )
    check("ruff passes on the HW10 code", lint.returncode == 0, (lint.stdout.strip().splitlines() or ["ok"])[-1])


def main():
    from code.hw10.judge import judge_settings

    banner("verify_hw10.py")
    print(f"started {datetime.now():%Y-%m-%d %H:%M:%S}\n", flush=True)
    safe("infrastructure", infra)
    safe("Part 1", part1)
    safe("Part 2", part2)
    safe("Part 3", part3)
    safe("Part 4", part4)
    safe("offline checks", offline)
    out = {
        "hw": "hw10",
        "sid4": SID4,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "commit_hash": run("git", "rev-parse", "HEAD") or "unknown",
        "tag": run("git", "tag", "--points-at", "HEAD") or "none",
        "config": CONFIG,
        "model": MODEL,
        "judge": judge_settings(),
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "all_passed": all(c["passed"] for c in CHECKS),
        "checks": CHECKS,
    }
    (REPORT_DIR / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    passed = sum(c["passed"] for c in CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed, saved reports/hw10/verification.json")


if __name__ == "__main__":
    main()
