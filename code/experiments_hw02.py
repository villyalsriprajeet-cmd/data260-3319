import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner_hw02 import run_with_retry
REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "reports" / "hw02" / "raw"
CASES = REPO / "reports" / "hw02" / "cases"
RAW.mkdir(parents=True, exist_ok=True)
def load_case(name):
    with open(CASES / name) as f:
        return json.load(f)
def classify(run):
    if not run["valid"]:
        return "hit_ceiling"
    if run["retries"] == 0:
        return "valid_first_attempt"
    if run["retries"] == 1:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"
def do_runs(case, n, ceiling, label):
    rows = []
    for i in range(1, n + 1):
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        run = run_with_retry(case["title"], case["content"], turn_ceiling=ceiling)
        outcome = classify(run)
        row = {
            "experiment": label,
            "run": i,
            "ceiling": ceiling,
            "timestamp": ts,
            "valid": run["valid"],
            "retries": run["retries"],
            "latency_ms": run["latency_ms"],
            "outcome": outcome,
            "tags": " | ".join(run["final"].get("tags", [])),
            "summary": run["final"].get("summary", ""),
        }
        rows.append(row)
        print(f"[{label}] run {i}/{n}: {outcome} "
              f"(retries={run['retries']}, {run['latency_ms']} ms)")
    return rows
def write_raw(rows, stem):
    csv_path = RAW / f"{stem}.csv"
    json_path = RAW / f"{stem}.json"
    fields = ["experiment", "run", "ceiling", "timestamp", "valid",
              "retries", "latency_ms", "outcome", "tags", "summary"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"  wrote {csv_path.name} and {json_path.name}")
def summarize(rows, label):
    n = len(rows)
    valid = [r for r in rows if r["valid"]]
    completion = len(valid) / n if n else 0
    latencies = [r["latency_ms"] for r in rows]
    mean_lat = int(statistics.mean(latencies)) if latencies else 0
    counts = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    print(f"\n=== {label} summary ===")
    print(f"  runs: {n}")
    print(f"  completion rate: {completion:.2%}")
    print(f"  mean latency: {mean_lat} ms")
    for k in ["valid_first_attempt", "valid_after_1_retry",
              "valid_after_2plus_retries", "hit_ceiling"]:
        print(f"  {k}: {counts.get(k, 0)}")
    return {"runs": n, "completion_rate": completion,
            "mean_latency_ms": mean_lat, "counts": counts}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True,
                    choices=["schema", "ceiling2", "ceiling10", "adversarial"])
    args = ap.parse_args()
    if args.experiment == "schema":
        case = load_case("schema_input.json")
        rows = do_runs(case, n=30, ceiling=10, label="schema30")
        write_raw(rows, "schema_runs")
        summarize(rows, "schema30")
    elif args.experiment == "ceiling2":
        case = load_case("schema_input.json")
        rows = do_runs(case, n=20, ceiling=2, label="ceiling2")
        write_raw(rows, "ceiling2_runs")
        summarize(rows, "ceiling2")
    elif args.experiment == "ceiling10":
        case = load_case("schema_input.json")
        rows = do_runs(case, n=20, ceiling=10, label="ceiling10")
        write_raw(rows, "ceiling10_runs")
        summarize(rows, "ceiling10")
    elif args.experiment == "adversarial":
        case = load_case("adversarial_input.json")
        rows = do_runs(case, n=5, ceiling=10, label="adversarial")
        write_raw(rows, "adversarial_runs")
        summarize(rows, "adversarial")
if __name__ == "__main__":
    main()