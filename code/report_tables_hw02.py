import json
import statistics
from pathlib import Path
RAW = Path(__file__).resolve().parent.parent / "reports" / "hw02" / "raw"
LABELS = [
    ("valid_first_attempt", "Valid first attempt"),
    ("valid_after_1_retry", "Valid after 1 retry"),
    ("valid_after_2plus_retries", "Valid after 2+ retries"),
    ("hit_ceiling", "Hit turn ceiling"),
]
def load(stem):
    with open(RAW / f"{stem}.json") as f:
        return json.load(f)
def table(rows, title):
    n = len(rows)
    valid = sum(1 for r in rows if r["valid"])
    completion = valid / n if n else 0
    all_lat = [r["latency_ms"] for r in rows]
    overall = int(statistics.mean(all_lat)) if all_lat else 0
    print(f"\n{title}")
    print(f"  runs: {n}   completion rate: {completion:.2%}   overall mean latency: {overall} ms\n")
    print(f"  {'Outcome over ' + str(n) + ' runs':<26}{'Count':<8}{'Mean latency (ms)'}")
    for key, pretty in LABELS:
        group = [r for r in rows if r["outcome"] == key]
        if group:
            mean_lat = str(int(statistics.mean([r["latency_ms"] for r in group])))
        else:
            mean_lat = "-"
        print(f"  {pretty:<26}{len(group):<8}{mean_lat}")
def ceiling_table():
    c2 = load("ceiling2_runs")
    c10 = load("ceiling10_runs")
    print("\nCeiling comparison (2 vs 10)\n")
    print(f"  {'Ceiling':<10}{'Runs':<7}{'Completion':<13}{'Mean latency (ms)'}")
    for name, rows in [("2", c2), ("10", c10)]:
        n = len(rows)
        comp = sum(1 for r in rows if r["valid"]) / n if n else 0
        mean_lat = int(statistics.mean([r["latency_ms"] for r in rows])) if rows else 0
        print(f"  {name:<10}{n:<7}{comp:<13.0%}{mean_lat}")
if __name__ == "__main__":
    table(load("schema_runs"), "Experiment 1 - 30-run schema test")
    ceiling_table()
    table(load("adversarial_runs"), "Experiment 3 - adversarial input (5 runs)")