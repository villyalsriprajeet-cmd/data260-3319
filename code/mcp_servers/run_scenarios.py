# HW5 Part 5: runs the agent on the local Ollama model for the metrics scenarios and saves the results
import json
from pathlib import Path
from agent import LOG_PATH, MODEL_NAME, run_agent
RAW_DIR = Path(__file__).resolve().parents[2] / "reports" / "hw05" / "raw"
SCENARIOS = [
    ("1. Search", "Find 3 fixtures for teams called Hawks.", 5),
    ("2. Detail lookup", "What is the venue and how many tickets are left for fixture FX-00042?", 5),
    ("3. Aggregate", "Which 3 cities have the most tickets available in total?", 5),
    ("4. Safety rule", "List 50 fixtures played at Gilroy Field.", 5),
    ("5. max_steps ceiling", "Search for Hawks fixtures, then look up the full details of the first one.", 1),
]
if __name__ == "__main__":
    LOG_PATH.write_text("")  # fresh log, so it matches this metrics run
    results = []
    for name, prompt, max_steps in SCENARIOS:
        r = run_agent(prompt, max_steps=max_steps)
        results.append({"scenario": name, "prompt": prompt, "max_steps": max_steps, **r})
        print(f"{name}: steps={r['steps']} stop={r['stop_reason']} tool_calls={r['tool_calls']}\n   answer: {r['answer'][:160]}\n")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "p5_scenarios.json").write_text(json.dumps({"model": MODEL_NAME, "results": results}, indent=2) + "\n")
    print(f"Model: {MODEL_NAME}")
    print("| Scenario | Steps | Stop reason | Tool calls |\n|---|---|---|---|")
    for r in results:
        print(f"| {r['scenario']} | {r['steps']} | {r['stop_reason']} | {r['tool_calls']} |")
    print(f"\nLog: {LOG_PATH}")