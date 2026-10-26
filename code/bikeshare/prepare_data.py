# HW7 Part 4: build the two scenario CSVs from one month of real Capital Bikeshare trip data (seeded, SEED 3319)
# usage: python -m code.bikeshare.prepare_data [YYYYMM]   (downloads from the public S3 bucket)
import csv
import hashlib
import io
import json
import random
import statistics
import sys
import urllib.request
import zipfile
from datetime import date

from .tools import ROOT, parse_time

SEED = 3319
BUCKET = "https://s3.amazonaws.com/capitalbikeshare-data"
OUT_DIR = ROOT / "data" / "bikeshare"
RAW_DIR = OUT_DIR / "raw"  # downloaded zips, git-ignored
SUMMARY_DIR = ROOT / "reports" / "hw07" / "raw"
SCENARIOS = {
    "scenario_membership": {
        "who": "member",
        "riders": 12,
        "per_rider": 45,
        "long_per_rider": 6,
        "rule": "12 commuters x 45 real member trips (39 of 8-40 min + 6 of 46-90 min)",
    },
    "scenario_payperuse": {
        "who": "casual",
        "riders": 250,
        "per_rider": 2,
        "long_per_rider": 0,
        "rule": "250 occasional riders x 2 real casual trips of 3-15 min",
    },
}


def candidate_months() -> list[str]:
    today, out = date.today(), []
    y, m = today.year, today.month
    for _ in range(14):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}{m:02d}")
    return out


def download(month: str) -> bytes | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{month}-capitalbikeshare-tripdata.zip"
    if path.exists():
        return path.read_bytes()
    url = f"{BUCKET}/{month}-capitalbikeshare-tripdata.zip"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            blob = resp.read()
    except Exception as exc:
        print(f"  {month}: not available ({exc})")
        return None
    path.write_bytes(blob)
    print(f"  {month}: downloaded {len(blob) / 1e6:.1f} MB from {url}")
    return blob


def read_trips(blob: bytes) -> tuple[list[dict], list[str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX"))
        text = z.read(name).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        try:
            r["_min"] = (parse_time(r["ended_at"]) - parse_time(r["started_at"])).total_seconds() / 60
        except (KeyError, ValueError):
            continue
        rows.append(r)
    return rows, reader.fieldnames


def build(rows: list[dict], spec: dict, rng: random.Random) -> list[dict]:
    pool = [r for r in rows if r.get("member_casual") == spec["who"]]
    if spec["who"] == "member":
        normal = [r for r in pool if 8 <= r["_min"] <= 40]
        long_ = [r for r in pool if 46 <= r["_min"] <= 90 and r.get("rideable_type") == "classic_bike"]
    else:
        normal, long_ = [r for r in pool if 3 <= r["_min"] <= 15], []
    n_long = spec["riders"] * spec["long_per_rider"]
    n_normal = spec["riders"] * spec["per_rider"] - n_long
    picked = rng.sample(normal, n_normal) + rng.sample(long_, n_long)
    long_set = {id(r) for r in picked[n_normal:]}
    rng.shuffle(picked)
    normals = [r for r in picked if id(r) not in long_set]
    longs = [r for r in picked if id(r) in long_set]
    out, width = [], len(str(spec["riders"]))
    for i in range(spec["riders"]):
        rid = f"{'R' if spec['who'] == 'member' else 'C'}{i + 1:0{width}d}"
        mine = (
            normals[
                i * (spec["per_rider"] - spec["long_per_rider"]) : (i + 1)
                * (spec["per_rider"] - spec["long_per_rider"])
            ]
            + longs[i * spec["long_per_rider"] : (i + 1) * spec["long_per_rider"]]
        )
        out += [{**r, "rider_id": rid} for r in mine]
    return sorted(out, key=lambda r: r["started_at"])


def summary(name: str, rows: list[dict], spec: dict, month: str, sha: str) -> dict:
    mins = [r["_min"] for r in rows]
    return {
        "scenario": name,
        "source_url": f"{BUCKET}/{month}-capitalbikeshare-tripdata.zip",
        "source_zip_sha256": sha,
        "seed": SEED,
        "construction": spec["rule"],
        "rows": len(rows),
        "riders": len({r["rider_id"] for r in rows}),
        "first_start": rows[0]["started_at"],
        "last_start": rows[-1]["started_at"],
        "duration_min": {
            "mean": round(statistics.mean(mins), 1),
            "median": round(statistics.median(mins), 1),
            "max": round(max(mins), 1),
            "over_45": sum(m > 45 for m in mins),
        },
        "rideable_type": {
            t: sum(r.get("rideable_type") == t for r in rows) for t in sorted({r.get("rideable_type") for r in rows})
        },
        "member_casual": {
            t: sum(r.get("member_casual") == t for r in rows) for t in sorted({r.get("member_casual") for r in rows})
        },
    }


def main() -> None:
    months = sys.argv[1:] or candidate_months()
    blob = month = None
    for m in months:
        blob = download(m)
        if blob:
            month = m
            break
    if not blob:
        raise SystemExit("no monthly file could be downloaded; pass a month like 202509")
    sha = hashlib.sha256(blob).hexdigest()
    rows, fields = read_trips(blob)
    prefix = f"{month[:4]}-{month[4:]}"
    rows = [r for r in rows if r["started_at"].startswith(prefix)]  # drop trips that began in the previous month
    print(f"source month {month}: {len(rows)} trips, sha256 {sha[:16]}...")
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in SCENARIOS.items():
        picked = build(rows, spec, rng)
        with open(OUT_DIR / f"{name}.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(fields) + ["rider_id"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(picked)
        info = summary(name, picked, spec, month, sha)
        (SUMMARY_DIR / f"p4_{name}_summary.json").write_text(json.dumps(info, indent=2) + "\n")
        print(
            f"{name}: {info['rows']} rows, {info['riders']} riders, mean {info['duration_min']['mean']} min, "
            f"{info['duration_min']['over_45']} over 45 min -> data/bikeshare/{name}.csv"
        )


if __name__ == "__main__":
    main()
