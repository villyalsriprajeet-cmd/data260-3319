# HW10 Part 4.1: one structured JSON span per stage, keyed by trace_id (the HW8 correlation_id)
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPANS_FILE = Path(os.getenv("HW10_SPANS_FILE", ROOT / "reports" / "hw10" / "traces" / "spans.jsonl"))
STAGE_ORDER = [
    "request",
    "cache_lookup",
    "inbox",
    "planner",
    "tasks",
    "writer",
    "drafts",
    "reviewer",
    "final",
    "evaluation",
]
QUEUE_STAGES = ["inbox", "tasks", "drafts", "final"]  # time a message waited in a Kafka topic


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def to_dt(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def duration_ms(start, end):
    return round((to_dt(end) - to_dt(start)).total_seconds() * 1000, 1)


def write_span(trace_id, stage, start, end, status="ok", error=None, service=None, **attrs):
    span = {
        "trace_id": trace_id,
        "stage": stage,
        "start": start,
        "end": end,
        "duration_ms": duration_ms(start, end),
        "status": status,
        "error": error,
        "service": service or stage,
        "pid": os.getpid(),
        "attrs": attrs,
    }
    SPANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SPANS_FILE, "a") as fh:
        fh.write(json.dumps(span, default=str) + "\n")  # one line per span, appended
    return span


def read_spans(path=SPANS_FILE):
    if not Path(path).exists():
        return []
    spans = []
    for line in Path(path).read_text().splitlines():
        try:
            spans.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip a torn or partial line
    return spans


def stage_rank(stage):
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER)


def trace_spans(trace_id, spans=None):
    found = [s for s in (spans if spans is not None else read_spans()) if s.get("trace_id") == trace_id]
    return sorted(found, key=lambda s: (stage_rank(s["stage"]), s["start"]))  # journey in stage order


def format_span(span):
    line = f"{span['stage']:<13} {span['start']}  {span['end']}  {span['duration_ms']:>10.1f} ms  {span['status']}"
    return line + (f"  error={span['error']}" if span.get("error") else "")
