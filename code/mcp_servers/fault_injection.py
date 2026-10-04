# HW5 Part 3 (Q20): 50 calls at 0%, 20% and 50% injected failure, seeded with VERIFY_SEED so the pattern repeats
import asyncio
import csv
import dataclasses
import hashlib
import json
import math
import time
from pathlib import Path
import league_server as ls
from faults import VERIFY_SEED, FaultInjector
RAW_DIR = Path(__file__).resolve().parents[2] / "reports" / "hw05" / "raw"
RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50
def pick_call(i: int):
    """Rotate through the three domain tools with valid inputs."""
    if i % 3 == 0:
        return "search_fixtures", {"query": "Hawks", "limit": 10}
    if i % 3 == 1:
        return "fixture_details", {"fixture_code": f"FX-{i + 1:05d}"}
    return "tickets_by_city", {"top_n": 5}
def p99(values: list[float]) -> float:
    """Nearest-rank p99: the value 99% of calls are at or below."""
    ordered = sorted(values)
    return ordered[math.ceil(0.99 * len(ordered)) - 1]
def expected_pattern(rate: float) -> list[str]:
    """Replay only the seeded coin flips (no database) to prove the same seed gives the same sequence."""
    rng, out = FaultInjector(rate, VERIFY_SEED).rng, []
    for _ in range(CALLS_PER_RATE):
        flips = []
        for _ in range(ls.RETRY_POLICY.max_attempts):
            flips.append(rng.random() < rate)
            if not flips[-1]:
                break
        out.append("".join("F" if f else "S" for f in flips))
    return out
async def main() -> None:
    store = ls.get_store()
    tools = {"search_fixtures": ls.search_fixtures, "fixture_details": ls.fixture_details, "tickets_by_city": ls.tickets_by_city}
    rows, summary = [], []
    for _ in range(3):
        await ls.tickets_by_city(5)  # warm up so the first timed call does not pay one off start up costs
    for rate in RATES:
        store.fault = FaultInjector(rate, VERIFY_SEED)  # fresh generator with the same seed for every rate
        latencies, successes, patterns = [], 0, []
        for i in range(CALLS_PER_RATE):
            name, args = pick_call(i)
            before = len(store.fault.history)
            start = time.perf_counter()
            result = await tools[name](**args)
            latency = (time.perf_counter() - start) * 1000
            pattern = "".join("F" if f else "S" for f in store.fault.history[before:])
            successes += result["ok"]
            latencies.append(latency)
            patterns.append(pattern)
            rows.append({"failure_rate": rate, "call": i + 1, "tool": name, "args": json.dumps(args), "ok": result["ok"],
                         "attempts": len(pattern), "attempt_pattern": pattern,
                         "error_code": result["error"]["code"] if result["error"] else "", "latency_ms": round(latency, 2)})
        summary.append({"failure_rate": rate, "calls": CALLS_PER_RATE, "success_rate": successes / CALLS_PER_RATE,
                        "mean_latency_ms": round(sum(latencies) / len(latencies), 2), "p99_latency_ms": round(p99(latencies), 2),
                        "total_attempts": sum(len(p) for p in patterns),
                        "sequence_sha256": hashlib.sha256(",".join(patterns).encode()).hexdigest()[:16],
                        "same_sequence_on_replay": patterns == expected_pattern(rate)})
    store.fault = None
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_DIR / "p3_fault_injection_calls.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)  # all 150 calls
    (RAW_DIR / "p3_fault_injection_summary.json").write_text(json.dumps(
        {"verify_seed": VERIFY_SEED, "retry_policy": dataclasses.asdict(ls.RETRY_POLICY), "db_timeout_s": ls.DB_TIMEOUT,
         "results": summary}, indent=2) + "\n")
    print(f"VERIFY_SEED={VERIFY_SEED}, {CALLS_PER_RATE} calls per rate, {len(rows)} calls total")
    print(f"{'Injected failure rate':<23}{'Success rate':<14}{'Mean latency (ms)':<19}{'p99 latency (ms)':<18}{'Attempts':<10}Same sequence")
    for s in summary:
        print(f"{s['failure_rate']:<23.0%}{s['success_rate']:<14.0%}{s['mean_latency_ms']:<19.2f}{s['p99_latency_ms']:<18.2f}"
              f"{s['total_attempts']:<10}{s['same_sequence_on_replay']}")
    print(f"Raw data: {RAW_DIR / 'p3_fault_injection_calls.csv'}")
if __name__ == "__main__":
    asyncio.run(main())