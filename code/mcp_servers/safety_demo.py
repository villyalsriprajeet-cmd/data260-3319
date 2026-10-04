# HW5 Part 5: one allowed and one blocked call through execute_tool to show the safety rule
import json
from tool_entry import MAX_AGENT_RESULTS, execute_tool
CALLS = [
    ("Allowed", "search_fixtures", {"query": "Gilroy Field", "limit": 5}),
    ("Blocked", "search_fixtures", {"query": "Gilroy Field", "limit": 50}),
]
if __name__ == "__main__":
    print(f"Safety rule: the assistant may get at most {MAX_AGENT_RESULTS} fixtures per search and may not use % or _ wildcards\n")
    for label, name, inputs in CALLS:
        result = json.loads(execute_tool(name, inputs))
        summary = {"ok": result["ok"], "data": f"{result['data']['count']} fixtures" if result["ok"] else None, "error": result["error"]}
        print(f"{label}: {name}({json.dumps(inputs)})\n  -> {json.dumps(summary)}\n")