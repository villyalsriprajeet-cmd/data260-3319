# HW5 Part 5: run_agent, a tool calling loop over the local Ollama model with a max_steps limit and a JSONL log
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from tool_entry import execute_tool
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"
VERIFY_SEED = 263319
MAX_STEPS = 5  # turn limit: one step = one model reply
LOG_PATH = Path(__file__).resolve().parents[2] / "reports" / "hw05" / "raw" / "agent_runs.jsonl"
SYSTEM_PROMPT = (
    "You are the assistant for a community sports league. Use the tools to look up fixtures, teams and tickets. "
    "Fixture codes look like FX-00001. Call a tool when you need data, then answer in one or two short sentences "
    "using only the tool results. If a tool returns ok false, tell the user the error instead of guessing."
)
# Tool descriptions sent to the model 
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_fixtures", "description": "Search fixtures whose title or venue contains the text.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "Text to look for, at least 2 characters, e.g. Hawks"},
            "limit": {"type": "integer", "description": "Maximum number of fixtures to return (1-50), default 10"}}}}},
    {"type": "function", "function": {
        "name": "fixture_details", "description": "Look up one fixture by its code, with its home team.",
        "parameters": {"type": "object", "required": ["fixture_code"], "properties": {
            "fixture_code": {"type": "string", "description": "Fixture code in the form FX-00001"}}}}},
    {"type": "function", "function": {
        "name": "tickets_by_city", "description": "Fixtures and tickets available per home-team city, highest total first.",
        "parameters": {"type": "object", "properties": {
            "top_n": {"type": "integer", "description": "How many cities to return (1-20), default 5"}}}}},
]
class OllamaModel:
    """Talks to the local Ollama server; temperature 0 and a fixed seed keep runs as repeatable as possible."""
    def __init__(self, model: str = MODEL_NAME, url: str = OLLAMA_URL, timeout: float = 120.0):
        self.name, self.url, self.timeout = model, url, timeout
    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {"model": self.name, "messages": messages, "tools": tools, "stream": False,
                   "options": {"temperature": 0, "seed": VERIFY_SEED}}
        response = httpx.post(self.url, json=payload, timeout=self.timeout, trust_env=False)  # local server, skip proxies
        response.raise_for_status()
        return response.json()["message"]  # {"role": "assistant", "content": ..., "tool_calls": [...]}
class MockModel:
    """Offline stand-in for the LLM: returns scripted replies in order, then keeps repeating the last one."""
    def __init__(self, replies: list[dict]):
        self.name, self.replies, self.calls = "mock", list(replies), 0
    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply
def log_event(path: Path, record: dict) -> None:
    """Append one JSON line to the run log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **record}
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
def run_agent(user_input: str, model=None, max_steps: int = MAX_STEPS, store=None, log_path: Path = LOG_PATH) -> dict:
    """Loop: ask the model, run any tool calls through execute_tool, stop on an answer, a safety block or max_steps."""
    model = model or OllamaModel()
    run_id = uuid.uuid4().hex[:8]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_input}]
    log_event(log_path, {"run_id": run_id, "event": "start", "model": model.name, "max_steps": max_steps, "user_input": user_input})
    steps, tool_calls, answer, stop_reason = 0, 0, "", "max_steps"
    while steps < max_steps:
        steps += 1  # turn counter
        start = time.perf_counter()
        try:
            reply = model.chat(messages, TOOL_SCHEMAS)
        except Exception as exc:
            answer, stop_reason = f"model error: {exc}", "model_error"
            log_event(log_path, {"run_id": run_id, "event": "model_error", "step": steps, "error": str(exc)})
            break
        calls = reply.get("tool_calls") or []
        log_event(log_path, {"run_id": run_id, "event": "step", "step": steps, "latency_ms": round((time.perf_counter() - start) * 1000),
                             "content": reply.get("content", ""), "requested_tools": [c["function"]["name"] for c in calls]})
        if not calls:
            answer, stop_reason = reply.get("content", ""), "completed"  # the model answered without needing a tool
            break
        messages.append({"role": "assistant", "content": reply.get("content", ""), "tool_calls": calls})
        blocked = None
        for call in calls:
            name, args = call["function"]["name"], call["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")  # some models send the arguments as a JSON string
            result = execute_tool(name, args, store=store)
            tool_calls += 1
            log_event(log_path, {"run_id": run_id, "event": "tool_call", "step": steps, "tool": name, "input": args, "result": json.loads(result)})
            messages.append({"role": "tool", "content": result, "tool_name": name})
            error = json.loads(result)["error"]
            if error and error["code"] == "SAFETY_BLOCKED":
                blocked = error["message"]
        if blocked:
            answer, stop_reason = f"I can't do that: {blocked}", "safety_block"  # stop the run instead of letting the model retry
            break
    if stop_reason == "max_steps":
        answer = f"stopped: reached max_steps ({max_steps}) before a final answer"
    log_event(log_path, {"run_id": run_id, "event": "stop", "stop_reason": stop_reason, "steps": steps, "tool_calls": tool_calls, "answer": answer})
    return {"run_id": run_id, "answer": answer, "stop_reason": stop_reason, "steps": steps, "tool_calls": tool_calls}
if __name__ == "__main__":
    import sys
    print(json.dumps(run_agent(" ".join(sys.argv[1:]) or "Which 3 cities have the most tickets available?"), indent=2))