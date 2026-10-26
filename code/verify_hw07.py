# HW7 self-check: smoke test of the tagged commit, writes reports/hw07/verification.json (never edits app code)
# usage: make verify-hw07   (MySQL + Ollama running; starts the API on PORT_BASE if it is not already up)
import json
import os
import random
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "code"))
REP, RAW = ROOT / "reports" / "hw07", ROOT / "reports" / "hw07" / "raw"
SID4 = 3319
CONFIG = {
    "SID4": SID4,
    "PORT_BASE": 8000 + SID4 % 900,
    "PREFIX": f"s{SID4}",
    "SEED": SID4,
    "VERIFY_SEED": 260000 + SID4,
    "DOMAIN_ID": SID4 % 8,
}
BASE = f"http://localhost:{CONFIG['PORT_BASE']}"
MODEL = {
    "llm": "qwen2.5:3b",
    "runtime": "Ollama (local)",
    "agent_temperature": 0,
    "agent_seed": SID4,
    "reliability_temperature": 0.7,
    "framework_part4": "LangGraph + langchain-ollama",
    "database": "MySQL s3319_rel",
    "auth": "JWT HS256, 30 min, roles reader/writer/moderator",
    "lint": "ruff + pre-commit",
}
load_dotenv(ROOT / "code" / "api" / ".env")
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
    print(("PASS" if ok else "FAIL"), "-", name, f"({detail})" if detail != "" else "")


def safe(name, fn):
    try:
        fn()
    except Exception as exc:  # one broken area must not stop the other checks
        check(name, False, f"{type(exc).__name__}: {exc}")


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def port_open(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def files_and_raw():
    need = [
        "pyproject.toml",
        ".pre-commit-config.yaml",
        "code/api/sql/004_hw07_jwt_roles.sql",
        "code/hw7_agent.py",
        "code/hw7_tasks.py",
        "code/hw7_reliability.py",
        "code/hw7_reflexion.py",
        "code/bikeshare/agent.py",
        "code/bikeshare/tools.py",
        "code/bikeshare/injection_eval.py",
        "code/hw7_file_tools.py",
        "reports/hw07/RUN_LOG.txt",
        "reports/hw07/METRICS.md",
        "reports/hw07/AI_USE.md",
        "reports/hw07/THREAT_MODEL.md",
        "reports/hw07/cases/agent_tasks.json",
        "reports/hw07/cases/hostile_pricing_override.html",
        "data/bikeshare/scenario_membership.csv",
        "data/bikeshare/scenario_payperuse.csv",
    ]
    missing = [f for f in need if not (ROOT / f).exists()]
    check("required code, report and case files exist", not missing, missing or f"{len(need)} files")
    rows = lambda name: (RAW / name).read_text().strip().splitlines()[1:]  # noqa: E731
    check(
        "Part 2: >= 20 reliability attempts saved",
        len(rows("p2_reliability_attempts.csv")) >= 20,
        f"{len(rows('p2_reliability_attempts.csv'))} attempts",
    )
    s = json.loads((RAW / "p2_reliability_summary.json").read_text())
    check(
        "Part 2: repair path raises the well-formed rate",
        s["rate_after"] >= s["rate_before"],
        f"{s['rate_before']:.0%} -> {s['rate_after']:.0%}",
    )
    c = json.loads((RAW / "p3_comparison_summary.json").read_text())
    check(
        "Part 3: comparison data saved (original vs Reflexion)",
        c["episodes"] >= 3,
        f"success {c['original']['task_success']} -> {c['reflexion']['task_success']} of {c['episodes']}",
    )
    refl = [json.loads(x) for x in (RAW / "p3_reflections.jsonl").read_text().splitlines() if x.strip()]
    check("Part 3: stored reflections include evidence", refl and all("evidence" in r for r in refl), len(refl))
    for scen, n in (("scenario_membership", 500), ("scenario_payperuse", 500)):
        info = json.loads((RAW / f"p4_{scen}_summary.json").read_text())
        check(f"Part 4: {scen} has >= {n} real trip rows", info["rows"] >= n, info["rows"])
    snaps = [json.loads(p.read_text()) for p in (RAW / "pricing_snapshots").glob("scenario_*.json")]
    ok = {s["run"].rsplit("_", 1)[0].replace("scenario_", "") for s in snaps if len(s.get("sha256", "")) == 64}
    check(
        "Part 4: pricing snapshot (url, date, sha256) saved for both scenarios",
        {"membership", "payperuse"} <= ok,
        sorted(ok),
    )
    att = json.loads((RAW / "p5_attack_results.json").read_text())
    check("Part 5: 3 attacks x 3 conditions recorded", len(att) == 9, len(att))
    both = [a for a in att if a["condition"] == "both"]
    check(
        "Part 5: no attack succeeds with prompt + tool defense",
        both and all(not a["outcome"].startswith("ATTACK") for a in both),
        [a["outcome"] for a in both],
    )
    gate = json.loads((RAW / "p6_gate_results.json").read_text())
    check(
        "Part 6: saved gate results are 10/10 correct",
        len(gate) == 10 and all(g["correct"] for g in gate),
        f"{sum(g['correct'] for g in gate)}/{len(gate)}",
    )


def lint():
    files = [str(p.relative_to(ROOT)) for p in (ROOT / "code").glob("hw7_*.py")] + ["code/bikeshare"]
    p = subprocess.run(["ruff", "check", *files], cwd=ROOT, capture_output=True, text=True)
    check("ruff passes on the HW7 code", p.returncode == 0, (p.stdout.strip().splitlines() or ["ok"])[-1])


def start_api():
    if port_open(CONFIG["PORT_BASE"]):
        return None
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "code.api.main:app", "--port", str(CONFIG["PORT_BASE"])],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(240):
        if port_open(CONFIG["PORT_BASE"]):
            break
        time.sleep(0.5)
    return proc


def token(user, pw):
    r = requests.post(f"{BASE}/auth/login", data={"username": user, "password": pw}, timeout=15)
    return r, (r.json().get("access_token") if r.ok else None)


def api_auth():
    r, w = token("s3319_writer", os.getenv("WRITER_PASSWORD", ""))
    check(
        "POST /auth/login valid credentials -> 200 + JWT",
        r.status_code == 200 and w and w.count(".") == 2,
        r.status_code,
    )
    r, _ = token("s3319_writer", "wrong-password")
    check("POST /auth/login invalid credentials -> 401", r.status_code == 401, r.status_code)
    check("GET /auth/me without token -> 401", requests.get(f"{BASE}/auth/me", timeout=10).status_code == 401)
    bad = requests.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer not.a.token"}, timeout=10)
    check("GET /auth/me invalid token -> 401", bad.status_code == 401, bad.status_code)
    _, rd = token("s3319_reader", os.getenv("READER_PASSWORD", ""))
    _, md = token("s3319_moderator", os.getenv("MODERATOR_PASSWORD", ""))
    me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {rd}"}, timeout=10)
    check("GET /auth/me with token -> 200 and role", me.ok and me.json().get("role") == "reader", me.status_code)
    roles_and_crud(rd, w, md)


def roles_and_crud(rd, w, md):
    H = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
    lst = requests.get(f"{BASE}/fixtures?limit=2", headers=H(rd), timeout=10)
    check("GET /fixtures as reader -> 200", lst.status_code == 200, lst.status_code)
    rng = random.Random(CONFIG["VERIFY_SEED"] + int(time.time()))
    body = {
        "fixture_title": "verify-hw07 fixture",
        "fixture_code": f"FX-8{rng.randint(1000, 9999)}",
        "venue": "Verify Field",
        "tickets_available": 1,
        "home_team_id": 1,
    }
    r = requests.post(f"{BASE}/fixtures", json=body, headers=H(rd), timeout=10)
    check("POST /fixtures as reader -> 403", r.status_code == 403, r.status_code)
    r = requests.post(f"{BASE}/fixtures", json=body, headers=H(w), timeout=10)
    check("POST /fixtures as writer -> 201", r.status_code == 201, r.status_code)
    fid = r.json().get("id") if r.status_code == 201 else None
    r = requests.delete(f"{BASE}/fixtures/{fid}", headers=H(w), timeout=10)
    check("DELETE /fixtures/{id} as writer -> 403", r.status_code == 403, r.status_code)
    r = requests.delete(f"{BASE}/fixtures/{fid}", headers=H(md), timeout=10)
    check("DELETE /fixtures/{id} as moderator -> 200 (test row removed)", r.status_code == 200, r.status_code)


def offline_tools():
    from bikeshare.tools import calculator, csv_sql  # noqa: E402
    from hw7_file_tools import confirm_bash, is_destructive  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "t.sqlite"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE trips (ride_id, duration_min)")
        con.executemany("INSERT INTO trips VALUES (?, ?)", [("ABCDEF0123456789", 5), ("0123456789ABCDEF", 50)])
        con.commit()
        con.close()
        sel = csv_sql("SELECT ride_id, duration_min FROM trips", db)
        check(
            "csv_sql: SELECT works and redacts ride_id",
            sel["success"] and sel["data"]["rows"][0]["ride_id"] == "[redacted]",
            sel.get("data", {}).get("row_count"),
        )
        dele = csv_sql("DELETE FROM trips", db)
        two = csv_sql("SELECT 1; DROP TABLE trips", db)
        left = sqlite3.connect(db).execute("SELECT COUNT(*) FROM trips").fetchone()[0]
        check(
            "csv_sql: DELETE and stacked statements rejected, data intact",
            not dele["success"] and not two["success"] and left == 2,
            f"rows left {left}",
        )
    calc = calculator("2 * (3 + 4) / 7")
    evil = calculator("__import__('os').system('ls')")
    check("calculator: safe arithmetic, code rejected", calc["data"]["value"] == 2.0 and not evil["success"])
    env = ["success", "ts"]
    check("tools return the common envelope", all(k in calc for k in env) and all(k in dele for k in env + ["error"]))
    cases = {
        "ls -la": "allow",
        "grep -n DEBUG a.py": "allow",
        "echo hacked > /etc/hosts": "block",
        "rm -r -f build/": "block",
        "ls && sudo mkfs.ext4 /dev/sdb1": "block",
    }
    ok = all(confirm_bash(c)["decision"] == d for c, d in cases.items()) and isinstance(is_destructive("ls"), bool)
    check("safety gate: allow-list, deny-list wins over safe prefix", ok)


def reflexion_selftest():
    from hw7_reflexion_selftest import run_selftest  # noqa: E402

    check("Part 3: Reflexion self-test (bounds, budget, isolation, injection) passes", run_selftest() == 0)


def agent_live():
    tags = requests.get("http://localhost:11434/api/tags", timeout=5).json()
    check("Ollama has qwen2.5:3b", any(m["name"] == MODEL["llm"] for m in tags.get("models", [])))
    from hw7_agent import run_agent  # noqa: E402
    from hw7_tasks import TASKS  # noqa: E402
    from hw7_tasks import check as task_check

    run = run_agent(TASKS["ERR"]["prompt"], verbose=False, log_path=None)
    passed, why = task_check("ERR", run)
    check(
        "hand-written agent loop completes a verification task (ERR)",
        passed and run["tool_calls"] >= 1,
        f"{why}; stop={run['stop_reason']} tool_calls={run['tool_calls']}",
    )


def main():
    print(f"=== HW7 verification | {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    safe("saved files and raw data", files_and_raw)
    safe("ruff passes on the HW7 code", lint)
    safe("offline tool and gate checks", offline_tools)
    safe("Reflexion self-test", reflexion_selftest)
    server = start_api()
    try:
        safe("live API auth and roles", api_auth)
    finally:
        if server:
            server.terminate()
    safe("live agent loop", agent_live)
    out = {
        "hw": "hw7",
        "sid4": SID4,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "commit_hash": git("rev-parse", "HEAD") or "unknown",
        "tag": git("describe", "--tags", "--exact-match") or "none",
        "config": CONFIG,
        "model": MODEL,
        "all_passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    REP.mkdir(parents=True, exist_ok=True)
    (REP / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed -> reports/hw07/verification.json")


if __name__ == "__main__":
    main()
