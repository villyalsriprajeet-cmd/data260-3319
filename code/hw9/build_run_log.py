# HW9: build reports/hw09/RUN_LOG.txt from the saved logs and raw files of the runs in the report
# usage (repo root): python -m code.hw9.build_run_log
import json
from code.kafka_service.settings import PORT_BASE, PREFIX, SID4, STUDENT_NAME
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HW9 = ROOT / "reports" / "hw09"


def section(title, body):
    return f"\n# {title}\n\n{body.rstrip()}\n"


def part4_lines(path):
    out = []
    for line in path.read_text().splitlines():
        r = json.loads(line)
        used = f"  lessons loaded: {', '.join(r['lessons_used'])}" if r["lessons_used"] else ""
        out.append(f"[{r['id']}] {r['question']}{used}")
        for a in r["attempts"]:
            fault = " (controlled fault)" if a["controlled_fault"] else ""
            out.append(f"  attempt {a['attempt']}{fault}: {a['result']}  {a['answer']}")
            if a["result"] == "REVISE":
                out.append(f"    evaluator: {a['explanation']}  feedback: {a['feedback']}")
        out.append(f"  final {r['final_result']} after {r['n_attempts']} attempt(s), {r['latency_s']} s")
    return "\n".join(out)


def main():
    parts = [
        f"HW9 RUN_LOG, {STUDENT_NAME}, SID4 {SID4}, PREFIX {PREFIX}, PORT_BASE {PORT_BASE}",
        f"Built {datetime.now():%Y-%m-%d %H:%M} from the saved logs and raw files of the runs in the report.",
        "Times inside the logs are UTC (they end in Z).",
    ]
    qa_log = HW9 / "logs" / "qa_service.log"
    if qa_log.exists():
        parts.append(
            section(
                "reports/hw09/logs/qa_service.log (Parts 2 and 3: cache hits, misses, agents, stale)",
                qa_log.read_text(),
            )
        )
    for name in ("p2_summary.json", "p3_sweep_summary.json", "p3_cost.json", "p3_stale_demo.json"):
        path = HW9 / "raw" / name
        if path.exists():
            parts.append(section(f"reports/hw09/raw/{name}", path.read_text()))
    for name in (
        "demo_repair",
        "training",
        "test_baseline",
        "test_evaluator_repair",
        "test_lesson_memory",
        "test_validated_improvement",
    ):
        path = HW9 / "part4" / "runs" / f"{name}.jsonl"
        if path.exists():
            parts.append(section(f"reports/hw09/part4/runs/{name}.jsonl", part4_lines(path)))
    for name in ("validation_report.json", "results_test.json"):
        path = HW9 / "part4" / name
        if path.exists():
            parts.append(section(f"reports/hw09/part4/{name}", path.read_text()))
    (HW9 / "RUN_LOG.txt").write_text("\n".join(parts) + "\n")
    print(f"wrote reports/hw09/RUN_LOG.txt ({sum(len(p) for p in parts):,} characters)")


if __name__ == "__main__":
    main()
