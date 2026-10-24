# HW7 Part 2 : 21 tool use attempts over the fixed tasks A, B, C with the same model settings
import csv
import json
import sys
from collections import Counter
from datetime import datetime

from hw7_agent import MODEL_NAME, ROOT, LocalModel, run_agent
from hw7_tasks import TASKS, check, save_cases

RAW = ROOT / "reports" / "hw07" / "raw"
VERIFY_SEED = 263319
TEMPERATURE = 0.7  # same for every attempt; only the seed changes, so failures can show up
CATEGORIES = ["malformed_args", "unknown_tool", "text_instead_of_tool", "lost_chain"]


def slots(calls: list[dict]) -> list[dict]:
    out, cur = [], None
    for c in calls:  # a slot = one needed call: its first try plus any repaired retries
        if cur is None:
            cur = {"first_valid": c["valid"], "final_valid": c["valid"]}
        cur["final_valid"] = c["valid"]
        if c["valid"]:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def classify(run: dict, passed: bool, reason: str) -> str:
    if passed:
        return "success"
    if run["stop_reason"] == "repair_failed":
        bad = [c["category"] for c in run["calls"] if not c["valid"]]
        return bad[-1] if bad else "repair_failed"
    return "answer_not_supported" if reason.startswith("answer") else "lost_chain"


def attempt(i: int, task_id: str) -> dict:
    seed = VERIFY_SEED + i
    run = run_agent(TASKS[task_id]["prompt"], model=LocalModel(temperature=TEMPERATURE, seed=seed), verbose=False)
    passed, reason = check(task_id, run)
    s = slots(run["calls"])
    cats = Counter(c["category"] for c in run["calls"] if not c["valid"])
    outcome = classify(run, passed, reason)
    row = {
        "attempt": i,
        "task": task_id,
        "seed": seed,
        "outcome": outcome,
        "check_reason": reason,
        "stop_reason": run["stop_reason"],
        "call_slots": len(s),
        "well_formed_first_try": sum(x["first_valid"] for x in s),
        "well_formed_after_repair": sum(x["final_valid"] for x in s),
        "repairs": run["repairs"],
        **{c: cats.get(c, 0) for c in CATEGORIES[:3]},
        "lost_chain": int(outcome == "lost_chain"),
        "tool_calls": run["tool_calls"],
        "tokens": run["tokens_in"] + run["tokens_out"],
        "latency_ms": run["latency_ms"],
    }
    print(
        f"{i:>2} {task_id}  seed {seed}  slots {row['call_slots']}  first-try ok {row['well_formed_first_try']}  "
        f"after repair ok {row['well_formed_after_repair']}  tools {row['tool_calls']}  -> {outcome}"
    )
    return {"row": row, "run": run}


def summarize(rows: list[dict]) -> dict:
    total = sum(r["call_slots"] for r in rows)
    before = sum(r["well_formed_first_try"] for r in rows)
    after = sum(r["well_formed_after_repair"] for r in rows)
    return {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "seeds": f"{VERIFY_SEED}+attempt",
        "attempts": len(rows),
        "task_success": sum(r["outcome"] == "success" for r in rows),
        "call_slots": total,
        "well_formed_before_repair": before,
        "well_formed_after_repair": after,
        "rate_before": round(before / total, 3) if total else 0,
        "rate_after": round(after / total, 3) if total else 0,
        "failures": {c: sum(r[c] for r in rows) for c in CATEGORIES},
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
    }


def main() -> None:
    per_task = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    save_cases()
    print(
        f"=== HW7 Part 2 reliability | {MODEL_NAME} temp {TEMPERATURE} | {per_task} x A,B,C | "
        f"{datetime.now():%Y-%m-%d %H:%M:%S} ==="
    )
    order = [t for _ in range(per_task) for t in ("A", "B", "C")]
    results = [attempt(i + 1, t) for i, t in enumerate(order)]
    rows = [r["row"] for r in results]
    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / "p2_reliability_attempts.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(RAW / "p2_reliability_runs.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r["run"], default=str) + "\n")
    summary = summarize(rows)
    (RAW / "p2_reliability_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"\nWell-formed call rate before repair: {summary['well_formed_before_repair']}/{summary['call_slots']}"
        f" = {summary['rate_before']:.1%}"
    )
    print(
        f"Well-formed call rate after repair:  {summary['well_formed_after_repair']}/{summary['call_slots']}"
        f" = {summary['rate_after']:.1%}"
    )
    print(f"Task success: {summary['task_success']}/{summary['attempts']}")
    print("Failures by type: " + ", ".join(f"{k}={v}" for k, v in summary["failures"].items()))
    print(f"Raw data: {RAW / 'p2_reliability_attempts.csv'}")


if __name__ == "__main__":
    main()
