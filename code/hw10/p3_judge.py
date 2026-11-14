# HW10 Parts 3.2 and 3.3: judge the 20 frozen drafts three times, compare with the human labels, measure repeatability
# usage (repo root): python -m code.hw10.p3_judge run      (3 runs x 20 drafts, resumable)
#                    python -m code.hw10.p3_judge report   (Spearman, mean absolute difference, score changes, CSV)
import argparse
import asyncio
import csv
import hashlib
import json
import statistics
import subprocess
import sys
from code.hw10.geval_metrics import HELPFULNESS_LEVELS, HELPFULNESS_STEPS, score
from code.hw10.judge import LocalJudge, judge_settings
from code.hw10.p3_cases import CASES_FILE, LABELS_FILE, load_labels
from code.hw10.traced_qa import ROOT
from code.hw10.tracing import now_iso
from code.kafka_service.settings import banner

EVAL_DIR = ROOT / "reports" / "hw10" / "eval"
RUNS_FILE = EVAL_DIR / "judge_runs.jsonl"
CSV_FILE = EVAL_DIR / "judge_validation.csv"
JSON_FILE = EVAL_DIR / "judge_validation.json"
RUNS = 3


def frozen_cases():
    data = json.loads(CASES_FILE.read_text())
    digest = hashlib.sha256(json.dumps(data["cases"], sort_keys=True).encode()).hexdigest()
    if digest != data["sha256"]:
        sys.exit("eval_cases.json does not match its sha256; the frozen drafts were changed")
    return data["cases"], digest


def check_committed():
    files = [str(CASES_FILE.relative_to(ROOT)), str(LABELS_FILE.relative_to(ROOT))]
    for f in files:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", f], cwd=ROOT, capture_output=True)
        changed = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", f], cwd=ROOT)
        if tracked.returncode != 0 or changed.returncode != 0:
            sys.exit(f"{f} must be committed and unchanged before the judge runs")
    log = ["git", "log", "-1", "--format=%h %cI %s", "--", files[1]]
    return subprocess.run(log, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load_runs():
    if not RUNS_FILE.exists():
        return []
    return [json.loads(line) for line in RUNS_FILE.read_text().splitlines() if line.strip()]


async def run_judge():
    cases, digest = frozen_cases()
    labels = load_labels()
    if len(labels) != len(cases):
        sys.exit(f"{len(labels)} human labels for {len(cases)} drafts; label all of them first")
    commit = check_committed()
    print(f"labels committed before judging: {commit}")
    print(f"judge settings: {judge_settings()}")
    done = {(r["run"], r["case_id"]) for r in load_runs() if r["status"] == "ok"}
    judge = LocalJudge()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    for run in range(1, RUNS + 1):
        print(f"\nrun {run} of {RUNS}", flush=True)
        for case in cases:
            if (run, case["case_id"]) in done:
                continue
            res = await score("helpfulness", case["question"], case["draft"], judge)
            row = {"run": run, "case_id": case["case_id"], "trace_id": case["trace_id"], "at": now_iso(), **res}
            row["cases_sha256"] = digest
            with open(RUNS_FILE, "a") as fh:
                fh.write(json.dumps(row) + "\n")  # saved after every score, so a rerun resumes
            why = res["reason"] or res["error"]
            print(f"  {case['case_id']} judge={res['score']}  {res['ms']:7.0f} ms  {why}", flush=True)
    print(f"\nsaved {RUNS_FILE.relative_to(ROOT)}; next: python -m code.hw10.p3_judge report")


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1  # ties share the average rank
        i = j + 1
    return out


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not sx or not sy:
        return None  # undefined when one side has no spread
    return round(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy), 4)


def mad(x, y):
    return round(statistics.mean(abs(a - b) for a, b in zip(x, y)), 4)


def compare(human, judge):
    exact = sum(a == b for a, b in zip(human, judge)) / len(human)
    within = sum(abs(a - b) <= 1 for a, b in zip(human, judge)) / len(human)
    return {
        "spearman": spearman(human, judge),
        "mean_abs_diff": mad(human, judge),
        "exact_agreement": round(exact, 4),
        "within_1_agreement": round(within, 4),
        "judge_mean": round(statistics.mean(judge), 3),
    }


def report():
    cases, digest = frozen_cases()
    labels = load_labels()
    latest = {}
    for r in load_runs():
        if r["status"] == "ok":
            latest[(r["run"], r["case_id"])] = r  # the last ok score for each run and case
    missing = [(run, c["case_id"]) for run in range(1, RUNS + 1) for c in cases if (run, c["case_id"]) not in latest]
    if missing:
        sys.exit(f"{len(missing)} scores missing, for example {missing[:3]}; run: python -m code.hw10.p3_judge run")
    rows, human = [], []
    by_run = {run: [] for run in range(1, RUNS + 1)}
    for c in cases:
        h = int(labels[c["case_id"]]["human_score"])
        s = [latest[(run, c["case_id"])]["score"] for run in range(1, RUNS + 1)]
        human.append(h)
        for run, v in zip(by_run, s):
            by_run[run].append(v)
        med = statistics.median(s)
        rows.append(
            {
                "case_id": c["case_id"],
                "trace_id": c["trace_id"],
                "question": c["user_question"],
                "human_score": h,
                "human_note": labels[c["case_id"]]["note"],
                **{f"judge_run{run}": v for run, v in zip(by_run, s)},
                "judge_median": med,
                "abs_diff_run1": abs(s[0] - h),
                "abs_diff_median": abs(med - h),
                "run_change": max(s) - min(s),
                "judge_reason_run1": latest[(1, c["case_id"])]["reason"],
            }
        )
    medians = [r["judge_median"] for r in rows]
    changes = [r["run_change"] for r in rows]
    pairs = [(a, b) for a in by_run for b in by_run if a < b]
    summary = {
        "created_at": now_iso(),
        "cases": len(rows),
        "runs": RUNS,
        "cases_sha256": digest,
        "labels_commit": check_committed(),
        "judge": judge_settings(),
        "criterion": "helpfulness",
        "rubric_steps": HELPFULNESS_STEPS,
        "rubric_levels": HELPFULNESS_LEVELS,
        "inputs": "question exactly as the Writer saw it (with MySQL facts) and the frozen Writer draft",
        "human_spread": {str(k): human.count(k) for k in range(1, 6)},
        "agreement_by_run": {f"run{run}": compare(human, v) for run, v in by_run.items()},
        "agreement_median": compare(human, medians),
        "repeatability": {
            "cases_with_any_change": sum(c > 0 for c in changes),
            "change_rate": round(sum(c > 0 for c in changes) / len(changes), 4),
            "mean_change": round(statistics.mean(changes), 4),
            "max_change": max(changes),
            "pairwise_change_rate": {
                f"run{a}_vs_run{b}": round(sum(x != y for x, y in zip(by_run[a], by_run[b])) / len(rows), 4)
                for a, b in pairs
            },
        },
    }
    with open(CSV_FILE, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    JSON_FILE.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{'case':<5} {'human':>5} {'run1':>5} {'run2':>5} {'run3':>5} {'diff':>5} {'change':>6}  question")
    for r in rows:
        runs = "".join(f"{r[f'judge_run{run}']:>6.1f}" for run in by_run)
        tail = f"{r['abs_diff_run1']:>5.1f} {r['run_change']:>6.1f}  {r['question']}"
        print(f"{r['case_id']:<5} {r['human_score']:>5}{runs} {tail}")
    for name, a in [*((k, v) for k, v in summary["agreement_by_run"].items()), ("median", summary["agreement_median"])]:
        print(
            f"\n{name:<7} Spearman={a['spearman']}  mean abs diff={a['mean_abs_diff']}  exact={a['exact_agreement']}"
            f"  within 1={a['within_1_agreement']}  judge mean={a['judge_mean']}",
            end="",
        )
    rep = summary["repeatability"]
    print(
        f"\n\nrepeatability over {RUNS} runs: {rep['cases_with_any_change']} of {len(rows)} cases changed "
        f"(rate {rep['change_rate']}), mean change {rep['mean_change']}, max change {rep['max_change']}"
    )
    print(f"pairwise change rates: {rep['pairwise_change_rate']}")
    print(f"\nsaved {CSV_FILE.relative_to(ROOT)} and {JSON_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "report"])
    args = parser.parse_args()
    banner(f"HW10 Parts 3.2 and 3.3 judge validation: {args.action}")
    asyncio.run(run_judge()) if args.action == "run" else report()
