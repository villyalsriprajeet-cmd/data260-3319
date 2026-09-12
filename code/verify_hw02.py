import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "code"))
SID4 = 3319
PORT_BASE = 8619
SEED = 3319
VERIFY_SEED = 263319
MODEL = "qwen2.5:3b"
checks = []
def check(name, condition):
    passed = bool(condition)
    checks.append({"check": name, "passed": passed})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    return passed
def get_commit_hash():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO),
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"
def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()
# Check 1: key files exist
check("agents_graph.py exists", (REPO / "code" / "agents_graph.py").exists())
check("schema_hw02.py exists", (REPO / "code" / "schema_hw02.py").exists())
check("runner_hw02.py exists", (REPO / "code" / "runner_hw02.py").exists())
check("FastAPI main.py exists", (REPO / "code" / "api" / "main.py").exists())
check("schema_input.json exists", (REPO / "reports" / "hw02" / "cases" / "schema_input.json").exists())
# Check 2: Pydantic schema behaves 
try:
    from schema_hw02 import validate_planner
    good = validate_planner({"tags": ["soccer match", "mountain west", "spartans"],
                             "summary": "A short valid summary."})[0]
    bad_count = validate_planner({"tags": ["only", "two"], "summary": "ok"})[0]
    bad_len = validate_planner({"tags": ["x", "mountain west", "spartans"], "summary": "ok"})[0]
    check("schema accepts a valid 3-tag output", good is True)
    check("schema rejects wrong tag count", bad_count is False)
    check("schema rejects out-of-range tag length", bad_len is False)
except Exception as e:
    check("schema accepts a valid 3-tag output", False)
    check("schema rejects wrong tag count", False)
    check("schema rejects out-of-range tag length", False)
# Check 3: LangGraph graph builds and compiles
try:
    from agents_graph import build_graph
    app = build_graph()
    check("LangGraph graph compiles", app is not None)
except Exception as e:
    check("LangGraph graph compiles", False)
# Check 4: FastAPI backend responds on PORT_BASE 
proc = None
try:
    if port_free(PORT_BASE):
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "code.api.main:app",
             "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started_here = True
    else:
        started_here = False
    ok = False
    for _ in range(20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT_BASE}/", timeout=2) as r:
                ok = (r.status == 200)
                break
        except Exception:
            time.sleep(0.5)
    check(f"FastAPI responds 200 on port {PORT_BASE}", ok)
finally:
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
# write verification.json
all_passed = all(c["passed"] for c in checks)
result = {
    "homework": "HW2",
    "SID4": SID4,
    "commit_hash": get_commit_hash(),
    "model": MODEL,
    "SEED": SEED,
    "VERIFY_SEED": VERIFY_SEED,
    "all_passed": all_passed,
    "checks": checks,
}
out_path = REPO / "reports" / "hw02" / "verification.json"
out_path.write_text(json.dumps(result, indent=2))
print("\n" + json.dumps(result, indent=2))
print(f"\nWrote {out_path}")