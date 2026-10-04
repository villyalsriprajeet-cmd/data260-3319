# HW5 self-check: smoke test of the API, database, both MCP servers, execute_tool and saved results, writes reports/hw05/verification.json
import asyncio
import csv
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[1]  # repo root
MCP_DIR = ROOT / "code" / "mcp_servers"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MCP_DIR))
REP = ROOT / "reports" / "hw05"
RAW = REP / "raw"
SID4 = 3319
CONFIG = {"SID4": SID4, "PORT_BASE": 8000 + SID4 % 900, "PREFIX": f"s{SID4}", "SEED": SID4,
          "VERIFY_SEED": 260000 + SID4, "DOMAIN_ID": SID4 % 8}
BASE = f"http://localhost:{CONFIG['PORT_BASE']}"
EMAIL = os.getenv("HW5_EMAIL", "prajeet@s3319.com")  # local test account
PASSWORD = os.getenv("HW5_PASSWORD", "Fixtures123")
MODEL = {"llm": "qwen2.5:3b", "runtime": "Ollama (local)", "temperature": 0, "max_steps": 5,
         "retry_policy": {"max_attempts": 3, "base_delay_s": 0.1, "max_delay_s": 1.0, "db_timeout_s": 5},
         "safety_rule": "search_fixtures limit <= 20, no % or _ wildcards"}
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
def load_json(path):
    return json.loads(Path(path).read_text())
# 1. required files
for f in ["code/mcp_servers/meals_server.py", "code/mcp_servers/league_server.py", "code/mcp_servers/envelope.py",
          "code/mcp_servers/retry.py", "code/mcp_servers/faults.py", "code/mcp_servers/tool_entry.py",
          "code/mcp_servers/agent.py", "code/mcp_servers/test_runner.py", "code/api/routers/teams.py",
          "code/api/sql/003_hw05_relationship.sql", "code/frontend/src/features/fixtures/fixturesSlice.js",
          "code/frontend/src/store/store.js", "reports/hw05/RUN_LOG.txt", "reports/hw05/METRICS.md",
          "reports/hw05/AI_USE.md", "reports/hw05/REFLECTION.md", "reports/hw05/report.pdf"]:
    check(f"file exists: {f}", (ROOT / f).exists())
# 2. saved MCP Inspector outputs
for f in ["p2a_search_meals_by_name", "p2a_meals_by_ingredient", "p2a_random_meal", "p2a_meal_details"]:
    try:
        load_json(RAW / f"{f}.json")
        check(f"raw/{f}.json is valid JSON", True)
    except Exception as e:
        check(f"raw/{f}.json is valid JSON", False, e)
for tool in ["search", "details", "aggregate"]:
    try:
        good, bad = load_json(RAW / f"p2b_{tool}_valid.json"), load_json(RAW / f"p2b_{tool}_invalid.json")
        check(f"raw p2b {tool}: valid call ok, invalid call rejected", good["ok"] and good["error"] is None
              and not bad["ok"] and bad["data"] is None and bad["error"]["code"] == "INVALID_INPUT", bad["error"])
    except Exception as e:
        check(f"raw p2b {tool} outputs readable", False, e)
# 3. fault injection raw data: 150 calls and the same seeded sequence on replay
try:
    from faults import FaultInjector
    rows = list(csv.DictReader(open(RAW / "p3_fault_injection_calls.csv")))
    rates = sorted({r["failure_rate"] for r in rows})
    check("raw fault data has 150 calls (3 rates x 50)", len(rows) == 150 and len(rates) == 3, f"{len(rows)} rows, rates {rates}")
    same = True
    for rate in rates:
        rng = FaultInjector(float(rate), CONFIG["VERIFY_SEED"]).rng  # replay the seeded coin flips only
        for r in (x for x in rows if x["failure_rate"] == rate):
            flips = ""
            for _ in range(3):
                flips += "F" if rng.random() < float(rate) else "S"
                if flips[-1] == "S":
                    break
            same &= flips == r["attempt_pattern"]
    check("VERIFY_SEED replay gives the same success/failure sequence", same)
    by_rate = {rate: sum(r["ok"] == "True" for r in rows if r["failure_rate"] == rate) / 50 for rate in rates}
    check("success rate falls as the failure rate rises", by_rate[rates[0]] >= by_rate[rates[1]] >= by_rate[rates[2]], by_rate)
except Exception as e:
    check("raw fault data readable", False, e)
# 4. agent run log
try:
    events = [json.loads(l) for l in open(RAW / "agent_runs.jsonl") if l.strip()]
    stops = [e for e in events if e["event"] == "stop"]
    reasons = {e["stop_reason"] for e in stops}
    check("agent_runs.jsonl has at least 4 runs", len(stops) >= 4, f"{len(stops)} runs")
    check("agent log shows completed, safety_block and max_steps stops", {"completed", "safety_block", "max_steps"} <= reasons, sorted(reasons))
    check("agent log records tool calls with input and result", any(e["event"] == "tool_call" and "input" in e and "result" in e for e in events))
except Exception as e:
    check("agent_runs.jsonl readable", False, e)
# 5. MySQL database
try:
    from sqlalchemy import text
    from code.api.database import engine
    with engine.connect() as c:
        fixtures = c.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
        teams = c.execute(text("SELECT COUNT(*) FROM teams")).scalar()
        rule = c.execute(text("SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
                              "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_fixtures_team'")).scalar()
    check("database connects to MySQL", True, engine.url.render_as_string(hide_password=True))
    check("fixtures and teams tables are filled", fixtures >= 5000 and teams >= 200, f"{fixtures} fixtures, {teams} teams")
    check("fixtures -> teams foreign key is ON DELETE RESTRICT", rule == "RESTRICT", rule)
except Exception as e:
    check("database reachable", False, e)
# 6. live API smoke test on PORT_BASE
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
    r = s.get(f"{BASE}/teams", timeout=10)
    check(f"backend responds on port {CONFIG['PORT_BASE']}", True)
    check("teams list without login returns 401", r.status_code == 401, r.status_code)
    r = s.post(f"{BASE}/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    check("login returns 200", r.status_code == 200, r.status_code)
    r = s.get(f"{BASE}/teams", params={"skip": 0, "limit": 5}, timeout=10)
    check("teams list is paginated", r.ok and len(r.json()) == 5, r.status_code)
    r = s.get(f"{BASE}/teams/1/fixtures", timeout=10)
    check("relationship query returns team 1's fixtures", r.ok and len(r.json()) > 0 and all(f["home_team_id"] == 1 for f in r.json()), r.status_code)
    r = s.post(f"{BASE}/fixtures", json={"fixture_title": "verify", "fixture_code": "bad-code", "venue": "v", "home_team_id": 1}, timeout=10)
    check("bad fixture_code format returns 422", r.status_code == 422, r.status_code)
    r = s.delete(f"{BASE}/teams/1", timeout=10)
    check("deleting a team that has fixtures returns 409", r.status_code == 409, r.status_code)
except Exception as e:
    check(f"backend responds on port {CONFIG['PORT_BASE']}", False, e)
finally:
    if server:
        server.terminate()
# 7. both MCP servers start over STDIO and answer a tool call
async def mcp_call(server_file, tool, args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / server_file)], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [t.name for t in (await session.list_tools()).tools]
            result = await session.call_tool(tool, args)
            return names, result.isError, result.content[0].text if result.content else ""
try:
    names, err, txt = asyncio.run(asyncio.wait_for(mcp_call("meals_server.py", "search_meals_by_name", {"query": "Arrabiata", "limit": 5}), 60))
    check("meals MCP server lists its 4 tools", sorted(names) == ["meal_details", "meals_by_ingredient", "random_meal", "search_meals_by_name"], names)
    check("meals MCP server answers search_meals_by_name", not err and "52771" in txt, txt[:80])
except Exception as e:
    check("meals MCP server starts and answers", False, e)
try:
    names, err, txt = asyncio.run(asyncio.wait_for(mcp_call("league_server.py", "tickets_by_city", {"top_n": 3}), 60))
    reply = json.loads(txt)
    check("league MCP server has exactly 3 tools", sorted(names) == ["fixture_details", "search_fixtures", "tickets_by_city"], names)
    check("league MCP server answers tickets_by_city in the {ok, data, error} envelope",
          set(reply) == {"ok", "data", "error"} and reply["ok"] and len(reply["data"]) == 3, txt[:80])
except Exception as e:
    check("league MCP server starts and answers", False, e)
# 8. execute_tool and the safety rule against the real database
try:
    from tool_entry import execute_tool
    allowed = json.loads(execute_tool("search_fixtures", {"query": "Field", "limit": 5}))
    blocked = json.loads(execute_tool("search_fixtures", {"query": "Field", "limit": 50}))
    check("execute_tool allows a search within the safety rule", allowed["ok"] and allowed["data"]["count"] == 5)
    check("execute_tool blocks a search that breaks the safety rule", not blocked["ok"] and blocked["error"]["code"] == "SAFETY_BLOCKED", blocked["error"])
except Exception as e:
    check("execute_tool runs", False, e)
# 9. offline test runner (no database, network or LLM)
try:
    p = subprocess.run([sys.executable, str(MCP_DIR / "test_runner.py")], cwd=ROOT, capture_output=True, text=True, timeout=120)
    summary = [l for l in p.stdout.splitlines() if "tests passed" in l]
    check("offline test runner passes every test", p.returncode == 0, summary[-1] if summary else p.stdout[-200:])
except Exception as e:
    check("offline test runner runs", False, e)
# 10. local model for Part 5
try:
    tags = requests.get("http://localhost:11434/api/tags", timeout=5).json()
    check("Ollama has qwen2.5:3b", any(m["name"] == MODEL["llm"] for m in tags.get("models", [])))
except Exception as e:
    check("Ollama reachable", False, e)

out = {"hw": "hw5", "generated": datetime.now().isoformat(timespec="seconds"),
       "commit_hash": git("rev-parse", "HEAD") or "unknown", "tag": git("describe", "--tags", "--exact-match") or "none",
       "config": CONFIG, "model": MODEL, "all_passed": all(c["passed"] for c in checks), "checks": checks}
REP.mkdir(parents=True, exist_ok=True)
(REP / "verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed -> reports/hw05/verification.json")