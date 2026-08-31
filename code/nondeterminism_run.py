import json
import csv
import time
from pathlib import Path
from agents_demo import make_llm, build_agents, run_pipeline
REPO = Path(__file__).resolve().parent.parent
CASE = REPO / "reports" / "hw01" / "cases" / "nondeterminism_input.json"
RAW = REPO / "reports" / "hw01" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
RUNS_PER_TEMP = 20
TEMPERATURES = [0.0, 0.7]
def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac
def summarise(runs):
    tag_sets = [tuple(r["tags"]) for r in runs]
    distinct = len(set(tag_sets))
    per_run = [set(r["tags"]) for r in runs]
    all_tags = set().union(*per_run) if per_run else set()
    in_all = sorted(t for t in all_tags if all(t in s for s in per_run))
    counts = {t: sum(1 for s in per_run if t in s) for t in all_tags}
    in_one = sorted(t for t, c in counts.items() if c == 1)
    lats = [r["latency_ms"] for r in runs]
    return {
        "distinct_tag_sets": distinct,
        "tags_in_all_runs": in_all,
        "tags_in_exactly_one_run": in_one,
        "latency_p50_ms": round(percentile(lats, 50), 1),
        "latency_p95_ms": round(percentile(lats, 95), 1),
        "latency_p99_ms": round(percentile(lats, 99), 1),
    }
def main():
    case = json.loads(CASE.read_text())
    title, content = case["title"], case["content"]
    print(f"Fixed input loaded: {title}\n")
    print(f"Starting {RUNS_PER_TEMP} runs x {len(TEMPERATURES)} temperatures = "
          f"{RUNS_PER_TEMP * len(TEMPERATURES)} total runs.\n")
    all_runs = []
    metrics = {}
    for temp in TEMPERATURES:
        print(f"\n Temperature {temp} : {RUNS_PER_TEMP} runs ")
        llm = make_llm(temp)
        planner, reviewer, finalizer = build_agents(llm)
        temp_runs = []
        for i in range(1, RUNS_PER_TEMP + 1):
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            t0 = time.time()
            result = run_pipeline(title, content, planner, reviewer, finalizer)
            latency_ms = int((time.time() - t0) * 1000)

            tags = result["final"]["data"]["tags"]
            summary = result["final"]["data"]["summary"]
            row = {
                "timestamp": stamp,
                "temperature": temp,
                "run": i,
                "tags": tags,
                "summary": summary,
                "latency_ms": latency_ms,
            }
            temp_runs.append(row)
            all_runs.append(row)
            (RAW / "all_runs.json").write_text(json.dumps(all_runs, indent=2))
            print(f"  [{stamp}] run {i:2d}/{RUNS_PER_TEMP}  {latency_ms:6d} ms  tags={tags}")
        metrics[str(temp)] = summarise(temp_runs)
    with open(RAW / "all_runs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "temperature", "run", "tag1", "tag2", "tag3", "summary", "latency_ms"])
        for r in all_runs:
            t = list(r["tags"]) + ["", "", ""]
            w.writerow([r["timestamp"], r["temperature"], r["run"], t[0], t[1], t[2], r["summary"], r["latency_ms"]])
    (RAW / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("\n\n METRICS ")
    for temp in TEMPERATURES:
        m = metrics[str(temp)]
        print(f"\nTemperature {temp}:")
        print(f"  Distinct tag sets       : {m['distinct_tag_sets']}")
        print(f"  Tags in all 20 runs     : {m['tags_in_all_runs']}")
        print(f"  Tags in exactly 1 run   : {m['tags_in_exactly_one_run']}")
        print(f"  Latency p50/p95/p99 ms  : {m['latency_p50_ms']} / {m['latency_p95_ms']} / {m['latency_p99_ms']}")
    print(f"\nSaved raw results to: {RAW}")
    print("  - all_runs.json")
    print("  - all_runs.csv")
    print("  - metrics.json")
if __name__ == "__main__":
    main()