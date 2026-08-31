import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
checks = []

def check(name, condition):
    checks.append({"check": name, "passed": bool(condition)})

check("index.html exists", (REPO / "code" / "web_application" / "index.html").exists())
check("script.js exists", (REPO / "code" / "web_application" / "script.js").exists())
check("style.css exists", (REPO / "code" / "web_application" / "style.css").exists())
check("Dockerfile exists", (REPO / "code" / "Dockerfile").exists())
check("agents_demo.py exists", (REPO / "code" / "agents_demo.py").exists())
check("nondeterminism_input.json exists", (REPO / "reports" / "hw01" / "cases" / "nondeterminism_input.json").exists())

raw = REPO / "reports" / "hw01" / "raw"
check("all_runs.json exists", (raw / "all_runs.json").exists())
check("all_runs.csv exists", (raw / "all_runs.csv").exists())
check("metrics.json exists", (raw / "metrics.json").exists())

try:
    runs = json.loads((raw / "all_runs.json").read_text())
    check("40 total runs recorded", len(runs) == 40)
except Exception:
    check("40 total runs recorded", False)

check("model_client.py exists", (REPO / "src" / "model_client.py").exists())
check("hw1_client.py exists", (REPO / "code" / "hw1_client.py").exists())
check("AGENT.md exists", (REPO / "AGENT.md").exists())
check("METRICS.md exists", (REPO / "reports" / "hw01" / "METRICS.md").exists())
check("AI_USE.md exists", (REPO / "reports" / "hw01" / "AI_USE.md").exists())
check("RUN_LOG.txt exists", (REPO / "reports" / "hw01" / "RUN_LOG.txt").exists())

all_passed = all(c["passed"] for c in checks)
result = {"all_passed": all_passed, "checks": checks}
(REPO / "reports" / "hw01" / "verification.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))