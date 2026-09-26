# HW4 self-check: smoke test of the app, database and saved results, writes reports/hw04/verification.json
import csv
import json
import os
import random
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import requests
from sqlalchemy import inspect, text
ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))
REP = ROOT / "reports" / "hw04"
SID4 = 3319
CONFIG = {"SID4": SID4, "PORT_BASE": 8000 + SID4 % 900, "PREFIX": f"s{SID4}", "SEED": SID4,
          "VERIFY_SEED": 260000 + SID4, "DOMAIN_ID": SID4 % 8}
BASE = f"http://localhost:{CONFIG['PORT_BASE']}"
EMAIL = os.getenv("HW4_EMAIL", "prajeet@s3319.com")  # local test account
PASSWORD = os.getenv("HW4_PASSWORD", "Fixtures123")
MODEL = {"llm": "qwen2.5:3b", "embed": "sentence-transformers/all-MiniLM-L6-v2", "vector_store": "FAISS",
         "chunk_size": 500, "chunk_overlap": 50, "top_k": 3}
checks = []
def check(name, ok, detail=""):
    checks.append({"check": name, "passed": bool(ok), "detail": str(detail)})
    print(("PASS" if ok else "FAIL"), "-", name, f"({detail})" if detail else "")
def port_open(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0
def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"
# 1. required files
for f in ["code/api/main.py", "code/api/database.py", "code/api/models.py", "code/api/security.py",
          "code/api/routers/auth.py", "code/api/routers/fixtures.py", "code/api/perf.py", "code/api/seed_hw04.py",
          "code/api/sql/001_schema.sql", "code/api/sql/002_add_index.sql", "code/measure_hw04.py", "code/rag/rag.py",
          "code/frontend/package.json", "code/frontend/src/App.jsx", "code/frontend/src/components/Login.jsx",
          "code/frontend/src/pages/Home.jsx", "code/frontend/src/pages/CreateRecord.jsx",
          "code/frontend/src/pages/UpdateRecord.jsx", "code/frontend/src/pages/DeleteRecord.jsx",
          "reports/hw04/RUN_LOG.txt", "reports/hw04/METRICS.md", "reports/hw04/AI_USE.md"]:
    check(f"file exists: {f}", (ROOT / f).exists())
# 2. saved N+1 raw data: 3 page sizes x 2 versions x 30 requests
try:
    rows = list(csv.DictReader(open(REP / "raw" / "n1_requests.csv")))
    cases = {(r["page_size"], r["version"]) for r in rows}
    check("raw N+1 data has 180 requests", len(rows) == 180, f"{len(rows)} rows")
    check("raw N+1 data covers 3 page sizes x 2 versions", len(cases) == 6, sorted(cases))
    naive = {int(r["sql_statements"]) for r in rows if r["version"] == "naive" and r["page_size"] == "200"}
    fixed = {int(r["sql_statements"]) for r in rows if r["version"] == "fixed" and r["page_size"] == "200"}
    check("raw data: naive runs more SQL than fixed at page 200", min(naive) > max(fixed), f"naive {naive}, fixed {fixed}")
except Exception as e:
    check("raw N+1 data readable", False, e)
# 3. saved RAG results
for f in ["rag_retrievals.txt", "rag_comparison.csv", "rag_ksweep.csv", "rag_eval.csv", "rag_eval_summary.md"]:
    check(f"RAG output exists: raw/{f}", (REP / "raw" / f).exists())
try:
    ev = list(csv.DictReader(open(REP / "raw" / "rag_eval.csv")))
    check("RAG eval covers 6 questions x 3 configs", len(ev) == 18, f"{len(ev)} rows")
    refused = [r["refused_when_needed"] for r in ev if r["config"] == "C" and r["qid"] in ("Q5", "Q6")]
    check("RAG config C refused Q5 and Q6", refused == ["True", "True"], refused)
    sweep_ks = [r["k"] for r in csv.DictReader(open(REP / "raw" / "rag_ksweep.csv"))]
    check("RAG top_k sweep ran k = 1, 3, 5", sweep_ks == ["1", "3", "5"], sweep_ks)
except Exception as e:
    check("RAG results readable", False, e)
# 4. MySQL database
try:
    from code.api.database import engine
    with engine.connect() as c:
        fixtures = c.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
        teams = c.execute(text("SELECT COUNT(*) FROM teams")).scalar()
        linked = c.execute(text("SELECT COUNT(DISTINCT home_team_id) FROM fixtures")).scalar()
        users = c.execute(text("SELECT COUNT(*) FROM users")).scalar()
    check("database connects via db_session_basede26 engine", True, engine.url.render_as_string(hide_password=True))
    check("fixtures table has at least 5,000 rows", fixtures >= 5000, fixtures)
    check("teams table has 200 rows, all linked", teams == 200 and linked == 200, f"{teams} teams, {linked} linked")
    check("users table has a login account", users >= 1, users)
    insp = inspect(engine)
    check("sessions table exists", "sessions" in insp.get_table_names())
    check("index idx_fixtures_venue exists", any(i["name"] == "idx_fixtures_venue" for i in insp.get_indexes("fixtures")))
except Exception as e:
    check("database reachable", False, e)
# 5. live API smoke test on PORT_BASE
server = None
if not port_open(CONFIG["PORT_BASE"]):  # start the backend if it is not already running
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "code.api.main:app", "--port", str(CONFIG["PORT_BASE"])],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if port_open(CONFIG["PORT_BASE"]):
            break
        time.sleep(0.5)
try:
    s = requests.Session()
    r = s.get(f"{BASE}/fixtures/naive", params={"limit": 10}, timeout=10)
    check(f"backend responds on port {CONFIG['PORT_BASE']}", True)
    check("list endpoint without login returns 401", r.status_code == 401, r.status_code)
    r = s.post(f"{BASE}/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    cookie = r.headers.get("set-cookie", "")
    check("login returns 200", r.status_code == 200, r.status_code)
    check("session cookie is HttpOnly", "session_id=" in cookie and "httponly" in cookie.lower())
    results = {}
    for v in ["naive", "fixed"]:
        r = s.get(f"{BASE}/fixtures/{v}", params={"limit": 10}, timeout=30)
        data = r.json() if r.ok else []
        results[v] = (data, int(r.headers.get("X-SQL-Count", "-1")))
        check(f"{v} list returns 10 fixtures with home_team", r.ok and len(data) == 10 and all(d.get("home_team") for d in data), r.status_code)
    check("naive and fixed return the same data", results["naive"][0] == results["fixed"][0])
    check("naive runs more SQL than fixed", results["naive"][1] > results["fixed"][1],
          f"naive {results['naive'][1]}, fixed {results['fixed'][1]}")
    rid = random.Random(CONFIG["VERIFY_SEED"]).randint(1, 5000)  # record picked with VERIFY_SEED
    r = s.get(f"{BASE}/fixtures/{rid}", timeout=10)
    check(f"GET by id works (id {rid} from VERIFY_SEED)", r.status_code in (200, 404), r.status_code)
    r = s.post(f"{BASE}/fixtures", json={"fixture_title": "verify_hw04 temp fixture", "venue": "verify venue"}, timeout=10)
    new = r.json() if r.status_code == 201 else {}
    check("POST creates a record with an id", r.status_code == 201 and "id" in new, r.status_code)
    if new:
        r = s.put(f"{BASE}/fixtures/{new['id']}", json={"fixture_title": "verify_hw04 updated", "venue": "verify venue"}, timeout=10)
        check("PUT updates the record", r.ok and r.json()["fixture_title"] == "verify_hw04 updated", r.status_code)
        r = s.delete(f"{BASE}/fixtures/{new['id']}", timeout=10)
        gone = s.get(f"{BASE}/fixtures/{new['id']}", timeout=10).status_code
        check("DELETE removes the temp record", r.ok and gone == 404, f"delete {r.status_code}, then get {gone}")
except Exception as e:
    check(f"backend responds on port {CONFIG['PORT_BASE']}", False, e)
finally:
    if server:
        server.terminate()
# 6. local model for Part 4
try:
    tags = requests.get("http://localhost:11434/api/tags", timeout=5).json()
    check("Ollama has qwen2.5:3b", any(m["name"] == MODEL["llm"] for m in tags.get("models", [])))
except Exception as e:
    check("Ollama reachable", False, e)

out = {"hw": "hw4", "generated": datetime.now().isoformat(timespec="seconds"),
       "commit_hash": git("rev-parse", "HEAD"), "tag": git("describe", "--tags", "--exact-match") or "none",
       "config": CONFIG, "model": MODEL, "all_passed": all(c["passed"] for c in checks), "checks": checks}
REP.mkdir(parents=True, exist_ok=True)
(REP / "verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed -> reports/hw04/verification.json")