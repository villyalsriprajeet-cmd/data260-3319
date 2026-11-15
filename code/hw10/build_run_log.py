# HW10: build reports/hw10/RUN_LOG.txt from the saved logs, spans and result files of the runs in the report
# usage (repo root): python -m code.hw10.build_run_log
import json
import subprocess
from code.hw10.tracing import format_span, read_spans, trace_spans
from code.kafka_service.settings import PORT_BASE, PREFIX, SID4, STUDENT_NAME
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HW10 = ROOT / "reports" / "hw10"
AGENTS_LOG = ROOT / "reports" / "hw08" / "logs" / "agents.log"


def section(title, body):
    return f"\n# {title}\n\n{body.rstrip()}\n"


def jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def agent_lines(since):
    kept, keep = [], False
    for line in AGENTS_LOG.read_text().splitlines():
        if line[:4].isdigit():
            keep = line[:24] >= since  # lines start with a UTC timestamp
        if keep:
            kept.append(line)
    return "\n".join(kept)


def eval_lines(rows):
    out = []
    for r in rows:
        f = r.get("final_vs_draft") or {}
        scores = [r[k]["score"] for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")]
        q = str((r.get("inputs") or {}).get("question", "")).split("\n\nFixture facts")[0]
        line = f"{r.get('evaluated_at')} {r['trace_id']} {r['status']} plan/draft/final={scores}"
        out.append(f"{line} difference={f.get('difference')} changed={f.get('draft_changed')}  {q}")
        if r.get("error"):
            out.append(f"  error: {r['error']}")
    return "\n".join(out)


def judge_lines(rows):
    return "\n".join(f"run {r['run']} {r['case_id']} score={r['score']} {r['status']}  {r['reason']}" for r in rows)


def main():
    spans = read_spans()
    since = min(s["start"] for s in spans) if spans else "2026-11-13"
    commits = subprocess.run(["git", "log", "--oneline", "-15"], cwd=ROOT, capture_output=True, text=True).stdout
    parts = [
        f"HW10 RUN_LOG, {STUDENT_NAME}, SID4 {SID4}, PREFIX {PREFIX}, PORT_BASE {PORT_BASE}",
        f"Built {datetime.now():%Y-%m-%d %H:%M} from the saved logs, spans and result files of the runs in the report.",
        "Times inside the logs are UTC (they end in Z).",
        section("git log (latest commits)", commits),
    ]
    qa_log = HW10 / "logs" / "qa.log"
    if qa_log.exists():
        parts.append(section("reports/hw10/logs/qa.log (cache lookups, sends, request results)", qa_log.read_text()))
    if AGENTS_LOG.exists():
        title = f"reports/hw08/logs/agents.log (Planner, Writer, Reviewer and Evaluator since {since})"
        parts.append(section(title, agent_lines(since)))
    ids_file = HW10 / "traces" / "trace_ids.json"
    if ids_file.exists():
        for label, info in json.loads(ids_file.read_text()).items():
            body = "\n".join(format_span(s) for s in trace_spans(info["trace_id"], spans))
            parts.append(section(f"Part 4.2 {label} trace {info['trace_id']} (from spans.jsonl)", body))
    rows = jsonl(HW10 / "eval" / "eval_results.jsonl")
    if rows:
        parts.append(section("reports/hw10/eval/eval_results.jsonl (one line per evaluation)", eval_lines(rows)))
    runs = jsonl(HW10 / "eval" / "judge_runs.jsonl")
    if runs:
        parts.append(section("reports/hw10/eval/judge_runs.jsonl (Part 3, 3 runs x 20 drafts)", judge_lines(runs)))
    for name in (
        "eval/judge_probe.json",
        "eval/human_labels.csv",
        "eval/judge_validation.csv",
        "eval/judge_validation.json",
        "latency/latency_per_request.csv",
        "latency/latency_summary.json",
        "verification.json",
    ):
        path = HW10 / name
        if path.exists():
            parts.append(section(f"reports/hw10/{name}", path.read_text()))
    (HW10 / "RUN_LOG.txt").write_text("\n".join(parts) + "\n")
    print(f"wrote reports/hw10/RUN_LOG.txt ({sum(len(p) for p in parts):,} characters)")


if __name__ == "__main__":
    main()
