# HW10 Part 4: send one question through the traced cache and agents, then print its spans in stage order
# usage (repo root): python -m code.hw10.ask --question "..." [--fault WRITER] [--no-eval] [--label miss]
import argparse
import asyncio
import json
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from code.hw10.traced_qa import ROOT, TracedQA
from code.hw10.tracing import format_span, trace_spans
from code.kafka_service.settings import banner

TRACE_IDS = ROOT / "reports" / "hw10" / "traces" / "trace_ids.json"


def save_label(label, result):
    saved = json.loads(TRACE_IDS.read_text()) if TRACE_IDS.exists() else {}
    saved[label] = {"trace_id": result["trace_id"], "path": result["path"], "status": result["request"]["status"]}
    TRACE_IDS.parent.mkdir(parents=True, exist_ok=True)
    TRACE_IDS.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"saved as '{label}' in {TRACE_IDS.relative_to(ROOT)}")


def show(result):
    req = result["request"]
    print(f"\ntrace_id: {result['trace_id']}")
    print(f"path: cache {result['path']}  (similarity {result['lookup']['similarity']})")
    print(f"status: {req['status']}  error: {req['error']}  failing_stage: {req['attrs'].get('failing_stage')}")
    print(f"answer: {result['answer']}")
    print("\nspans for this trace_id, in stage order:")
    print(f"  {'stage':<13} {'start':<24}  {'end':<24}  {'duration':>13}  status")
    for span in trace_spans(result["trace_id"]):
        print("  " + format_span(span))


async def main(args):
    banner("HW10 traced request")
    qa = TracedQA()
    await qa.start()
    try:
        result = await qa.ask(args.question, wait_eval=not args.no_eval, fault=args.fault, timeout=args.timeout)
    finally:
        await qa.stop()
    show(result)
    if args.label:
        save_label(args.label, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--fault", choices=["PLANNER", "WRITER", "REVIEWER"], help="make that agent fail on purpose")
    parser.add_argument("--no-eval", action="store_true", help="stop at the final answer, skip the evaluator")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--label", help="save the trace_id under this name, e.g. hit, miss or failed")
    asyncio.run(main(parser.parse_args()))
