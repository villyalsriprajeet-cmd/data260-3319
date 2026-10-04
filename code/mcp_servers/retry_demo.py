# HW5 Part 3 (Q19): shows the retry policy on a real fixture_details call in three cases
import asyncio
import json
import time
from pathlib import Path
import league_server as ls
from faults import FaultInjector
RAW_DIR = Path(__file__).resolve().parents[2] / "reports" / "hw05" / "raw"
CASES = [
    ("1. Success on the first attempt", [False]),
    ("2. Failure on the first attempt, success after a retry", [True, False]),
    ("3. Failure on every allowed attempt", [True, True, True]),
]
async def main() -> None:
    store = ls.get_store()
    lines = [f"Retry policy: {ls.RETRY_POLICY.max_attempts} attempts, backoff {ls.RETRY_POLICY.base_delay * 1000:.0f} ms doubling, "
             f"max {ls.RETRY_POLICY.max_delay * 1000:.0f} ms, DB timeout {ls.DB_TIMEOUT} s per attempt", ""]
    for title, plan in CASES:
        store.fault = FaultInjector(plan=plan)  # fixed outcomes so each case is shown on purpose
        start = time.perf_counter()
        result = await ls.fixture_details("FX-00001")
        elapsed = (time.perf_counter() - start) * 1000
        pattern = " -> ".join("fail" if f else "ok" for f in store.fault.history)
        shown = dict(result, data={k: result["data"][k] for k in ("fixture_code", "fixture_title")}) if result["ok"] else result
        lines += [title, f"  attempts: {pattern}", f"  time: {elapsed:.0f} ms", f"  result: {json.dumps(shown)}", ""]
    store.fault = None
    text = "\n".join(lines)
    print(text)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "p3_retry_demo.txt").write_text(text + "\n")  # saved so the run can be checked later
if __name__ == "__main__":
    asyncio.run(main())