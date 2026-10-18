# HW6 self-check: read-only smoke test, writes reports/hw06/verification.json
import json
import random
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "code"))
REP = ROOT / "reports" / "hw06"
RAW = REP / "raw"
SID4 = 3319
CONFIG = {"SID4": SID4, "PORT_BASE": 8000 + SID4 % 900, "PREFIX": f"s{SID4}", "SEED": SID4,
          "VERIFY_SEED": 260000 + SID4, "DOMAIN_ID": SID4 % 8}
BASE = f"http://localhost:{CONFIG['PORT_BASE']}"
MODEL = {"llm": "qwen2.5:3b", "runtime": "Ollama (local)", "temperature": 0, "seed": CONFIG["SEED"], "num_ctx": 4096,
         "database": "MongoDB 7.0 (Docker s3319_mongo)", "short_term_n": 12, "summarize_every_user_msgs": 5,
         "episodic_top_k": 3, "embedder": "all-MiniLM-L6-v2", "file_memory_max_lines": 40, "file_memory_max_age_h": 24}
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
        return ""
# 1. required files
for f in ["AGENT.md", "MEMORY.md", "MEMORY_CONSOLIDATION_LOG.md", "code/file_memory.py", "code/hw6_memory_cli.py",
          "code/check_agent_rules.py", "code/api/mongo_db.py", "code/api/memory.py", "code/api/routers/docs.py",
          "code/api/routers/chat.py", "code/hw6_sweep.py", "reports/hw06/RUN_LOG.txt", "reports/hw06/METRICS.md",
          "reports/hw06/AI_USE.md", "reports/hw06/report.pdf", "reports/hw06/memory_probes.yaml",
          "reports/hw06/raw/chat_metrics.csv", "reports/hw06/raw/sweep_turns.csv", "reports/hw06/raw/probe_results.json",
          "reports/hw06/raw/sweep_summary.json"]:
    check(f"file exists: {f}", (ROOT / f).exists())
# 2. Part 3 raw data
try:
    import yaml
    check("memory_probes.yaml parses", bool(yaml.safe_load((REP / "memory_probes.yaml").read_text())))
    rows = (RAW / "sweep_turns.csv").read_text().strip().splitlines()[1:]
    check("sweep_turns.csv has 120 rows (4 settings x 30 turns)", len(rows) == 120, len(rows))
    for name in ("probe_results.json", "sweep_summary.json"):
        text = (RAW / name).read_text()
        json.loads(text)
        check(f"{name} is valid JSON with all 4 settings", all(k in text for k in ("n4", "n12", "n30", "evict")))
except Exception as e:
    check("Part 3 raw data readable", False, e)
# 3. MongoDB collections and validators
try:
    from code.api.mongo_db import get_db
    db = get_db()
    names = set(db.list_collection_names())
    check("MongoDB has fixtures, messages, summaries and episodes", {"fixtures", "messages", "summaries", "episodes"} <= names, sorted(names))
    rules = {c["name"]: "validator" in c.get("options", {}) for c in db.list_collections()}
    check("each collection has a $jsonSchema validator", all(rules.get(n) for n in ("fixtures", "messages", "summaries", "episodes")), rules)
except Exception as e:
    check("MongoDB reachable", False, e)
# 4. file memory: prompt, commands, AGENT.md rules, consolidation replay
try:
    import file_memory as fm
    import hw6_memory_cli as cli
    prompt = fm.build_system_prompt(fm.load_agent(), fm.load_memory())
    check("system prompt contains AGENT.md and MEMORY.md", "AGENT.md" in prompt and "Long-term memory" in prompt)
    check("CLI offers /memory /compact /dream /help", all(c in cli.HELP for c in ("/memory", "/compact", "/dream", "/help")))
    mem = fm.load_memory()
    check("current MEMORY.md has under 40 content lines", len(fm.content_lines(mem)) < 40, len(fm.content_lines(mem)))
    p = subprocess.run([sys.executable, "-m", "code.check_agent_rules"], cwd=ROOT, capture_output=True, text=True)
    check("AGENT.md rule checker passes", p.returncode == 0, p.stdout.strip().splitlines()[-1] if p.stdout else p.stderr[-120:])
    commits = git("log", "--reverse", "--format=%H", "--", "MEMORY.md").split()
    check("MEMORY.md has at least 2 commits (original and consolidated)", len(commits) >= 2, len(commits))
    original = git("show", f"{commits[0]}:MEMORY.md")
    check("committed original MEMORY.md is 55 lines", len(original.splitlines()) == 55, len(original.splitlines()))
    new_text, log = fm.consolidate(original)
    kinds = [x.split(" |")[0] for x in log]
    check("replaying consolidation on the original gives under 40 lines", len(fm.content_lines(new_text)) < 40, len(fm.content_lines(new_text)))
    check("replay merges at least 3 duplicates and resolves at least 3 contradictions",
          kinds.count("MERGED duplicate") >= 3 and kinds.count("CONTRADICTION") >= 3, f"{kinds.count('MERGED duplicate')} merges, {kinds.count('CONTRADICTION')} contradictions")
    check("replay flags the hedged contradiction for review", "REVIEW" in kinds)
except Exception as e:
    check("file memory checks run", False, e)
# 5. Ollama
try:
    tags = requests.get("http://localhost:11434/api/tags", timeout=5).json()
    check("Ollama has qwen2.5:3b", any(m["name"] == MODEL["llm"] for m in tags.get("models", [])))
except Exception as e:
    check("Ollama reachable", False, e)
# 6. live API smoke test on PORT_BASE
server = None
if not port_open(CONFIG["PORT_BASE"]):  # start the backend if it is not already running
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "code.api.main:app", "--port", str(CONFIG["PORT_BASE"])],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if port_open(CONFIG["PORT_BASE"]):
            break
        time.sleep(0.5)
try:
    rng = random.Random(CONFIG["VERIFY_SEED"])
    title = f"verify-fixture-{rng.randint(1000, 9999)}"
    r = requests.get(f"{BASE}/api/fixtures", timeout=10)
    check(f"backend responds on port {CONFIG['PORT_BASE']}", r.ok, r.status_code)
    body = {"fixture_title": title, "category": "League", "kickoff_at": "2026-11-01T14:00:00Z"}
    r = requests.post(f"{BASE}/api/fixtures", json=body, timeout=10)
    fid = r.json().get("id") if r.status_code == 201 else None
    check("POST /api/fixtures creates a document (201)", r.status_code == 201, r.status_code)
    check("GET /api/fixtures/{id} returns it", fid and requests.get(f"{BASE}/api/fixtures/{fid}", timeout=10).json()["fixture_title"] == title)
    r = requests.put(f"{BASE}/api/fixtures/{fid}", json={"status": "Live"}, timeout=10)
    check("PUT /api/fixtures/{id} changes only the sent field", r.ok and r.json()["status"] == "Live" and r.json()["fixture_title"] == title, r.status_code)
    r = requests.post(f"{BASE}/api/fixtures", json={**body, "category": "Chess"}, timeout=10)
    check("invalid category is rejected with 422", r.status_code == 422, r.status_code)
    r = requests.delete(f"{BASE}/api/fixtures/{fid}", timeout=10)
    check("DELETE /api/fixtures/{id} removes it", r.status_code in (200, 204) and requests.get(f"{BASE}/api/fixtures/{fid}", timeout=10).status_code == 404, r.status_code)
    user = f"verify-{CONFIG['VERIFY_SEED']}"
    r = requests.post(f"{BASE}/api/chat", json={"user_id": user, "session_id": "verify-session", "message": "Hi, I manage the Spartans."}, timeout=300)
    check("POST /api/chat returns a reply", r.status_code == 200 and bool(r.json().get("reply", "").strip()), r.status_code)
    r = requests.get(f"{BASE}/api/memory/{user}", timeout=30)
    check("GET /api/memory/{user_id} shows the stored messages", r.ok and len(r.json()["recent_messages"]) >= 2, r.status_code)
except Exception as e:
    check(f"backend responds on port {CONFIG['PORT_BASE']}", False, e)
finally:
    if server:
        server.terminate()

out = {"hw": "hw6", "sid4": SID4, "generated": datetime.now().isoformat(timespec="seconds"),
       "commit_hash": git("rev-parse", "HEAD") or "unknown", "tag": git("describe", "--tags", "--exact-match") or "none",
       "config": CONFIG, "model": MODEL, "all_passed": all(c["passed"] for c in checks), "checks": checks}
REP.mkdir(parents=True, exist_ok=True)
(REP / "verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed -> reports/hw06/verification.json")
