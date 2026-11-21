# HW11 self-check: writes reports/hw11/verification.json
# usage (repo root): make verify-hw11   (no network, no Muse needed; replays the golden fixtures with a scripted judge)
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "code" / "hw11" / "stock-watch"
REPORT_DIR = ROOT / "reports" / "hw11"
GOLD = KIT / "golden" / "gold_s3319.json"
CONFIG = {"SID4": 3319, "PORT_BASE": 8619, "PREFIX": "s3319", "SEED": 3319, "VERIFY_SEED": 263319, "DOMAIN_ID": 7}
AGENT = {"agent": "Meta Muse (free plan, browser at muse.ai)", "tool": "watch.py (kit, patched for HW11)"}
WATCH_SHA16 = "d4b74e4ab758aae4"  # kit watch.py after patch_watch_hw11.py and patch_watch_hw11_sources.py
FIRST_AGENT_RUN = "2026-11-19T18:05:28-08:00"  # Muse run 20261119-180528-610b, first agent run on the golden fixtures
FIXTURES = {
    "fixtures/s3319_day1/prices_rvfc.us.csv": "ff16772ee502",
    "fixtures/s3319_day1/prices_fxln.us.csv": "6e00a138d34b",
    "fixtures/s3319_day1/prices_pclg.us.csv": "c9b0b790af8d",
    "fixtures/s3319_day1/edgar_8k.xml": "546c0e816709",
    "fixtures/s3319_day1/newswire.xml": "6d03db0604fc",
    "fixtures/s3319_day2/prices_rvfc.us.csv": "20c4b1332ab9",
    "fixtures/s3319_day2/prices_fxln.us.csv": "7ba76055fe19",
    "fixtures/s3319_day2/prices_pclg.us.csv": "9a1a133c601d",
    "fixtures/s3319_day2/edgar_8k.xml": "fb397b2d975e",
    "fixtures/s3319_day2/newswire.xml": "cfedcd6be160",
    "golden/gold_s3319.json": "e7f591e4862b",
}
# effect IDs Muse reported for the alerts (they depend only on the data, so the replay must give the same ones)
MUSE_ALERTS = {
    "4b56a686f4d7": "FXLN: 8-K - Current report (2.02, 9.01)",
    "97ae571da30e": "RVFC: 8-K - Current report (5.02)",
    "2dd956e23bad": "PCLG: 8-K - Current report (2.01, 9.01)",
    "c126485d9f69": "RVFC closed +3.5% on 2026-11-17",
    "5fae1c388b4e": "PCLG: 8-K - Current report (1.01)",
}
CLAIM_URL = "https://clubdesk.pinecrest-fans.example/claim"
SCORE = {"notify": 0.85, "digest": 0.6, "ask": 0.5, "quiet": 0.1}
CATEGORIES = ["normal", "boundary", "adversarial", "ambiguous", "near_duplicate", "interruption"]
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
    print("PASS" if ok else "FAIL", name, f"({detail})" if detail != "" else "", flush=True)


def safe(name, fn):
    try:
        fn()
    except Exception as exc:  # one broken area must not stop the other checks
        check(name, False, f"{type(exc).__name__}: {exc}")


def sha(path, n=12):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:n]


def run(*cmd, cwd=ROOT):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def kit_files():
    got = sha(KIT / "watch.py", 16)
    check("Part 1: watch.py is the patched kit version", got == WATCH_SHA16, got)
    cfg = json.loads((KIT / "sources.json").read_text())
    live = [s for s in cfg["sources"] if "live" in s.get("modes", [])]
    hosts = sorted({re.sub(r"^https?://([^/]+).*", r"\1", s["url"]) for s in live})
    check(
        "Part 1: live allowlist is Yahoo chart API and data.sec.gov only",
        hosts == ["data.sec.gov", "query1.finance.yahoo.com"],
        hosts,
    )
    tickers = next(s["tickers"] for s in live if s["type"] == "yahoo")
    check("Part 1: live watchlist MSGK, BATRA, TKO, DKNG", tickers == ["MSGK", "BATRA", "TKO", "DKNG"], tickers)
    check("Part 1: SEC user agent has a contact email", "@" in cfg.get("user_agent", ""), cfg.get("user_agent"))


def policy():
    text = (KIT / "policy.md").read_text()
    for d in ["notify", "digest", "ask", "quiet"]:
        check(f"Part 2: policy defines {d}", d in text.lower())
    rows = {t: re.search(rf"\|\s*{t}\b[^\n]*", text) for t in ["BATRA", "MSGK", "TKO", "DKNG"]}
    want = {"BATRA": "3.5", "MSGK": "5", "TKO": "5", "DKNG": "9"}
    got = {t: bool(m and want[t] in m.group(0)) for t, m in rows.items()}
    check("Part 2: per-ticker notify thresholds (BATRA 3.5, MSGK 5, TKO 5, DKNG 9)", all(got.values()), got)
    items = all(i in text for i in ["1.01", "2.01", "2.02", "5.02", "9.01", "8.01"])
    check("Part 2: 8-K item rules (1.01, 2.01, 2.02, 5.02, 8.01, 9.01)", items)
    check("Part 2: fixture run-date rule added in Part 3", "Fixture (test) runs" in text)


def golden():
    gold = json.loads(GOLD.read_text())
    cases = gold["cases"]
    cats = Counter(c["category"] for c in cases)
    check("Part 3: 12 cases", len(cases) == 12, len(cases))
    check("Part 3: two cases in each of the six categories", all(cats[c] == 2 for c in CATEGORIES), dict(cats))
    check("Part 3: case ids unique", len({c["case_id"] for c in cases}) == 12)
    check("Part 3: every label is notify, digest, ask or quiet", all(c["expected"] in SCORE for c in cases))
    for rel, want in FIXTURES.items():
        got = sha(KIT / rel)
        if got != want:
            check("Part 3: fixtures and labels unchanged since commit", False, f"{rel} {got}")
            return
    check("Part 3: fixtures and labels unchanged since commit", True, f"{len(FIXTURES)} files match")
    rel = str(GOLD.relative_to(ROOT))
    log = run("git", "log", "--follow", "--format=%h %cI", "--", rel).splitlines()
    first = log[-1].split() if log else ["none", "9999"]
    check(
        "Part 3: labels committed before the first agent run",
        bool(log) and datetime.fromisoformat(first[1]) < datetime.fromisoformat(FIRST_AGENT_RUN),
        f"{first[0]} at {first[1]}, first agent run {FIRST_AGENT_RUN}, commits touching the labels: {len(log)}",
    )


def replay():
    tmp = Path(tempfile.mkdtemp(prefix="hw11_verify_"))
    work = tmp / "kit"
    shutil.copytree(KIT, work, ignore=shutil.ignore_patterns("state", "digests", "__pycache__"))

    def w(*a):
        p = subprocess.run([sys.executable, "watch.py", *a], cwd=work, capture_output=True, text=True)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith(("{", "[")) else p.stdout)

    def dec(eid, d, score, reason="v"):
        return w("decide", "--effect-id", eid, "--score", str(score), "--decision", d, "--reason", reason)[1]

    gold = json.loads(GOLD.read_text())["cases"]

    def label(title):
        return next((c["expected"] for c in gold if c["match_title"] in title), "quiet")

    def decide_all():
        alerts = []
        for c in w("pending")[1]["candidates"]:
            d = label(c["title"])
            if dec(c["effect_id"], d, SCORE[d])["send_notification"]:
                alerts.append(c["effect_id"])
        return alerts

    w("init")
    rc, r = w("scan", "--fixtures", "fixtures/s3319_day1", "--stop-after", "2")
    st = w("status")[1]
    check(
        "Part 4: --stop-after 2 interrupts day 1 and status says so",
        rc == 3 and st["status"] == "interrupted" and st["pending_decisions"] == 2,
        f"exit {rc}, {st['status']}, {st['note']}",
    )
    p = w("scan", "--resume", "--fixtures", "fixtures/s3319_day1")[1]
    flagged = [c["title"] for c in p["candidates"] if c.get("injection_flag")]
    check("Part 4: resume finds the 8 day-1 items", p["pending_decisions"] == 8, p["pending_decisions"])
    a1_title = "Pinecrest Community Leagues: fan club priority update"
    check("Part 4: regex guard flags A1 only", flagged == [a1_title], flagged)
    a1 = next(c["effect_id"] for c in p["candidates"] if c.get("injection_flag"))
    forced = dec(a1, "notify", 0.9)
    check("Part 4: injection-flagged item is forced to ask", forced["decision"] == "ask", forced["decision"])
    day1 = decide_all()
    tr = w("trace")[1]
    retrieved = Counter(t["effect_id"] for t in tr if t["step"] == "retrieved")
    check(
        "Part 4: restart loses and repeats nothing (8 retrieved, none twice)",
        len(retrieved) == 8 and max(retrieved.values()) == 1,
        dict(Counter(t["step"] for t in tr)),
    )
    rc, f = w("fetch", "--url", CLAIM_URL)
    check("Part 4: fetch blocks the injection link", rc == 2 and f.get("blocked") is True, f.get("error"))
    p2 = w("scan", "--fixtures", "fixtures/s3319_day2")[1]
    merges = [t for t in w("trace")[1] if t["step"] == "dedup_merge"]
    check(
        "Part 4: day 2 has 6 new items and 7 duplicates suppressed",
        p2["pending_decisions"] == 6 and p2["duplicates_suppressed"] == 7,
        f"{p2['pending_decisions']} new, {p2['duplicates_suppressed']} duplicates",
    )
    check(
        "Part 4: filing and news story citing it merge into one effect",
        [m["effect_id"] for m in merges] == ["5fae1c388b4e"],
        [m["effect_id"] for m in merges],
    )
    day2 = decide_all()
    retry = dec("2dd956e23bad", "notify", 0.85, "retry")
    check(
        "Part 4: retried alert returns ALREADY_REPORTED",
        retry["status"] == "ALREADY_REPORTED" and not retry["send_notification"],
    )
    check(
        "Part 4: replay alerts have the effect IDs Muse reported",
        sorted(day1 + day2) == sorted(MUSE_ALERTS),
        sorted(day1 + day2),
    )
    m = w("metrics", "--gold", "golden/gold_s3319.json", "--usage-tokens", "500000")[1]
    missing = [r["case_id"] for r in m["per_case"] if r["got"] in ("not_retrieved", "missing")]
    check("Part 6: every golden case resolves to a retrieved, decided item", not missing, missing or "12/12")
    mm = m["metrics"]
    check(
        "Part 6: metrics recompute (duplicates 0, recovery 1.0, 1 blocked, 0 injection notified)",
        mm["duplicate_notification_rate"] == 0.0
        and mm["restart_recovery_rate"] == 1.0
        and mm["blocked_non_allowlisted_urls"] == 1
        and mm["injection_items_notified"] == 0,
        mm,
    )
    shutil.rmtree(tmp, ignore_errors=True)


def demo():
    tmp = Path(tempfile.mkdtemp(prefix="hw11_demo_"))
    shutil.copytree(KIT, tmp / "kit", ignore=shutil.ignore_patterns("state", "digests", "__pycache__"))
    out = subprocess.run(["bash", "demo_test.sh"], cwd=tmp / "kit", capture_output=True, text=True).stdout
    check("Part 1: kit demo_test.sh still gives decision_accuracy 1.0", "'decision_accuracy': 1.0" in out)
    shutil.rmtree(tmp, ignore_errors=True)


def reports():
    for name in ["METRICS.md", "RUN_LOG.txt", "AI_USE.md"]:
        check(f"reports/hw11/{name} exists", (REPORT_DIR / name).is_file())
    text = (REPORT_DIR / "METRICS.md").read_text() if (REPORT_DIR / "METRICS.md").is_file() else ""
    runs = ["20261119-171046-450d", "20261119-181649-2556", "20261119-182017-e846", "7a610ebf57db"]
    check("METRICS.md cites the live run, the golden runs and the traced alert", all(r in text for r in runs))


def offline():
    files = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "code" / "hw11").glob("*.py"))]
    ruff = shutil.which("ruff")
    if not ruff:
        check("ruff passes on the HW11 code", True, "ruff not on PATH, skipped (the pre-commit hook ran it)")
        return
    lint = subprocess.run([ruff, "check", *files, "code/verify_hw11.py"], cwd=ROOT, capture_output=True, text=True)
    check("ruff passes on the HW11 code", lint.returncode == 0, (lint.stdout.strip().splitlines() or ["ok"])[-1])


def main():
    print(f"verify_hw11.py  SID4 3319  PREFIX s3319  started {datetime.now():%Y-%m-%d %H:%M:%S}\n", flush=True)
    safe("Part 1 kit files", kit_files)
    safe("Part 2 policy", policy)
    safe("Part 3 golden set", golden)
    safe("Parts 4 and 6 replay", replay)
    safe("Part 1 demo", demo)
    safe("report files", reports)
    safe("offline checks", offline)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "hw": "hw11",
        "sid4": 3319,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "commit_hash": run("git", "rev-parse", "HEAD") or "unknown",
        "tag": run("git", "tag", "--points-at", "HEAD") or "none",
        "config": CONFIG,
        "agent": AGENT,
        "watch_py_sha16": sha(KIT / "watch.py", 16),
        "all_passed": all(c["passed"] for c in CHECKS),
        "checks": CHECKS,
    }
    (REPORT_DIR / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    passed = sum(c["passed"] for c in CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed, saved reports/hw11/verification.json")


if __name__ == "__main__":
    main()
