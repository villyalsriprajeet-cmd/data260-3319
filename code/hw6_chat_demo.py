# HW6 Part 2 demo: sends a scripted 12-message conversation to POST /api/chat and prints what memory was used
import json
import sys
import urllib.request
BASE = "http://127.0.0.1:8619"
USER = sys.argv[1] if len(sys.argv) > 1 else "sri3319"
SESSION = sys.argv[2] if len(sys.argv) > 2 else "demo-session-1"
MESSAGES = [
    "Hi, my name is Sri and I manage the Spartans.",
    "My favorite team is the Spartans and we play at Spartan Soccer Complex.",
    "We usually play on Saturday mornings at 9 AM.",
    "Our rival is the Hawks and we play them next week.",
    "I prefer short reminders by email, not text messages.",
    "Which venue do we play at?",
    "Who is our rival?",
    "What day and time do we usually play?",
    "How should you remind me about fixtures?",
    "What is my name and which team do I manage?",
    "Which team do I support?",
    "Please summarize what you know about me.",
]
def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)
for i, text in enumerate(MESSAGES, 1):
    out = post("/api/chat", {"user_id": USER, "session_id": SESSION, "message": text})
    used = out["used"]
    print(f"\n[{i}] USER: {text}")
    print(f"    ASSISTANT: {out['reply']}")
    print(f"    short-term msgs used: {used['short_term_count']} | summary used: {bool(used['long_term_summary'])} | new facts: {used['new_facts_saved']}")
    print(f"    episodic facts retrieved: {[f['fact'] for f in used['episodic_facts']]}")
    print(f"    prompt tokens: {out['metrics']['prompt_tokens']} | latency: {out['metrics']['latency_ms']} ms")
