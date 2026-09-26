# HW4 Part 3: time naive vs fixed list endpoints (3 page sizes x 2 versions x 30 requests = 180)
import csv
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
import requests
BASE = "http://localhost:8619"  # PORT_BASE
EMAIL, PASSWORD = "prajeet@s3319.com", "Fixtures123"  # local test account
PAGE_SIZES = [10, 50, 200]
VERSIONS = ["naive", "fixed"]
REQUESTS_PER_CASE = 30
WARMUP = 3  # unrecorded requests per case before measuring
RAW_DIR = Path(__file__).resolve().parents[1] / "reports" / "hw04" / "raw"
def pct(values, p):
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]  # p-th percentile
def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()  # keeps the session cookie between requests
    s.post(f"{BASE}/login", json={"email": EMAIL, "password": PASSWORD}).raise_for_status()

    for size in PAGE_SIZES:  # warm-up, not recorded
        for v in VERSIONS:
            for _ in range(WARMUP):
                s.get(f"{BASE}/fixtures/{v}", params={"limit": size})
    rows = []
    for size in PAGE_SIZES:
        for i in range(1, REQUESTS_PER_CASE + 1):
            for v in VERSIONS:  # alternate naive and fixed so both run under the same conditions
                t0 = time.perf_counter()
                resp = s.get(f"{BASE}/fixtures/{v}", params={"limit": size})
                ms = (time.perf_counter() - t0) * 1000  # end-to-end latency in ms
                rows.append({"timestamp": datetime.now().isoformat(timespec="milliseconds"),
                             "page_size": size, "version": v, "request_no": i,
                             "status": resp.status_code, "rows_returned": len(resp.json()),
                             "sql_statements": int(resp.headers["X-SQL-Count"]), "latency_ms": round(ms, 3)})
    with open(RAW_DIR / "n1_requests.csv", "w", newline="") as f:  # all 180 measured requests
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for size in PAGE_SIZES:
        for v in VERSIONS:
            case = [r for r in rows if r["page_size"] == size and r["version"] == v]
            lat = [r["latency_ms"] for r in case]
            summary.append({"page_size": size, "version": v, "requests": len(case),
                            "sql_per_request": statistics.mean(r["sql_statements"] for r in case),
                            "p50_ms": round(pct(lat, 50), 2), "p95_ms": round(pct(lat, 95), 2),
                            "p99_ms": round(pct(lat, 99), 2)})
    for size in PAGE_SIZES:  # speed-up = naive p50 / fixed p50
        naive, fixed = [x for x in summary if x["page_size"] == size]
        naive["speedup_p50"] = fixed["speedup_p50"] = round(naive["p50_ms"] / fixed["p50_ms"], 2)
    with open(RAW_DIR / "n1_summary.json", "w") as f:
        json.dump({"run_at": datetime.now().isoformat(timespec="seconds"), "base_url": BASE,
                   "requests_total": len(rows), "warmup_per_case": WARMUP, "cases": summary}, f, indent=2)
    print(f"[{datetime.now().isoformat(timespec='seconds')}] measured {len(rows)} requests")
    print("| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |")
    print("|---|---|---|---|---|---|")
    for x in summary:
        print(f"| {x['page_size']} | {x['version']} | {x['sql_per_request']:g} | {x['p50_ms']} | {x['p95_ms']} | {x['p99_ms']} |")
    for size in PAGE_SIZES:
        print(f"page {size}: fixed is {[x for x in summary if x['page_size'] == size][0]['speedup_p50']}x faster (p50)")
if __name__ == "__main__":
    main()