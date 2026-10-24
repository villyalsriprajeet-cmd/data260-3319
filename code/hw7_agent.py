# HW7 Part 2: hand written agent loop over the HW1 ModelClient and the three HW5 domain tools
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # HW1 model adapter
sys.path.insert(0, str(ROOT / "code" / "mcp_servers"))  # HW5 tools and execute_tool
from tool_entry import execute_tool

from model_client import ModelClient

logging.getLogger("league").setLevel(logging.WARNING)  # our own tool log replaces the HW5 server log
MODEL_NAME = "qwen2.5:3b"
SEED = 3319
MAX_ITERS = 6  # hard ceiling on model turns per run
MAX_FAILED_REPAIRS = 2  # bad calls after a repair prompt before a clean stop
LOG_PATH = ROOT / "reports" / "hw07" / "raw" / "agent_runs.jsonl"
CODE_RE = r"^FX-\d{5}$"
CODE_FIND = re.compile(r"FX-\d{5}")
SYSTEM_PROMPT = (
    "You are the assistant for a community sports league. Use the tools to look up fixtures, teams and tickets. "
    "Work step by step: call one tool, read its result, then call the next tool the question still needs. "
    "If the question has several parts (for example 'then ...'), make a tool call for each part and do not answer "
    "until every part has a tool result. Fixture codes look like FX-00001; only use codes that appear in tool results. "
    "When you have every fact the question asks for, answer in two or three short sentences using only values from "
    "tool results (never guess a value), "
    "and include the fixture codes you used. If a tool returns ok false, tell the user what went wrong."
)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_fixtures",
            "description": "Search fixtures whose title or venue contains the text.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 2, "description": "Text to look for, e.g. Hawks"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Max fixtures (1-20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fixture_details",
            "description": "Look up one fixture by its code, with its home team.",
            "parameters": {
                "type": "object",
                "required": ["fixture_code"],
                "additionalProperties": False,
                "properties": {
                    "fixture_code": {"type": "string", "pattern": CODE_RE, "description": "Code like FX-00001"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tickets_by_city",
            "description": "Fixtures and tickets available per home-team city, highest first.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "top_n": {"type": "integer", "minimum": 1, "maximum": 20, "description": "How many cities (1-20)"}
                },
            },
        },
    },
]
SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOL_SCHEMAS}


class LocalModel:
    def __init__(self, temperature: float = 0.0, seed: int = SEED):
        self.name = MODEL_NAME
        self.client = ModelClient(model=MODEL_NAME, temperature=temperature, num_ctx=4096, num_predict=300, seed=seed)

    def chat(self, messages: list[dict]) -> dict:
        return self.client.complete(messages, tools=TOOL_SCHEMAS, json_mode=False)


def check_value(name: str, rule: dict, value) -> str | None:
    want = rule.get("type")
    if want == "string" and not isinstance(value, str):
        return f"'{name}' must be a string, got {type(value).__name__}"
    if want == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return f"'{name}' must be an integer, got {type(value).__name__}"
    if want == "string" and len(value.strip()) < rule.get("minLength", 0):
        return f"'{name}' must be at least {rule['minLength']} characters"
    if "pattern" in rule and not re.match(rule["pattern"], value):
        return f"'{name}' must match {rule['pattern']} (e.g. FX-00001), got '{value}'"
    if want == "integer" and not rule.get("minimum", value) <= value <= rule.get("maximum", value):
        return f"'{name}' must be between {rule['minimum']} and {rule['maximum']}, got {value}"
    return None


def validate_call(name: str, raw_args) -> tuple[dict | None, str | None, str | None]:
    if name not in SCHEMAS:
        return None, f"unknown tool '{name}'; available: {', '.join(SCHEMAS)}", "unknown_tool"
    args = raw_args
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError as exc:
            return None, f"arguments are not valid JSON ({exc.msg})", "malformed_args"
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object", "malformed_args"
    schema = SCHEMAS[name]
    extra = sorted(set(args) - set(schema["properties"]))
    missing = [k for k in schema.get("required", []) if k not in args]
    if extra or missing:
        return None, f"unknown argument(s) {extra} / missing required {missing}", "malformed_args"
    for key, value in args.items():
        problem = check_value(key, schema["properties"][key], value)
        if problem:
            return None, f"schema validation failed: {problem}", "malformed_args"
    return args, None, None


def log_event(path: Path | None, record: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **record}
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def short(result: dict) -> str:
    if not result["ok"]:
        return f"error {result['error']['code']}: {result['error']['message']}"
    data = result["data"]
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]["fixture_code"] if data["results"] else "-"
        return f"ok: {data['count']} fixture(s), first {first}"
    if isinstance(data, list):
        return f"ok: {len(data)} row(s), top {data[0] if data else '-'}"
    return f"ok: {data.get('fixture_code')} '{data.get('fixture_title')}', tickets {data.get('tickets_available')}"


INCOMPLETE_PROMPT = (
    "Your answer is not finished: it stops before giving what the question asks for. "
    "Call the tool you still need (search_fixtures finds fixtures by any text, such as a city, team or venue name), "
    "then give the complete answer."
)
UNFINISHED = re.compile(r":\s*$|\b(let['’]?s|let me|i will|i'll|i am going to|i'm going to)\b", re.I)


def incomplete(text: str) -> bool:
    text = text.strip()
    return not text or bool(UNFINISHED.search(text))  # empty, or announces a step it never took


def repair_prompt(problems: list[str]) -> str:
    return (
        "Your last tool call could not be run: " + "; ".join(problems) + ". "
        "Send one corrected tool call using exactly the tool names and argument names in the tool list."
    )


def new_state(user_input: str, context_note: str | None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_note:  # Part 3 reflection: passed as clearly labelled untrusted data, never as instructions
        messages.append({"role": "user", "content": context_note})
    messages.append({"role": "user", "content": user_input})
    return {
        "messages": messages,
        "seen_codes": set(CODE_FIND.findall(user_input.upper())),
        "nudged": False,
        "calls": [],
        "slots": [],
        "failed_streak": 0,
        "tool_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "repairs": 0,
        "answer": "",
        "stop_reason": "max_iters",
    }


def grounding_problem(name: str, args: dict, seen: set[str]) -> str | None:
    code = args.get("fixture_code", "").strip().upper() if name == "fixture_details" else ""
    if code and code not in seen:  # a guessed code: not in the question and not in any earlier tool result
        return (
            f"fixture_code {code} does not appear in the question or in any earlier tool result; "
            "call search_fixtures (with a city, team or venue name) to get real fixture codes first"
        )
    return None


def run_calls(st: dict, step: int, calls: list, store, run_id: str, verbose: bool) -> list[str]:
    problems, good = [], []
    seen = set(st["seen_codes"])  # codes the model could actually have seen before this turn
    for call in calls:
        fn = call.get("function", {})
        name, raw = fn.get("name", ""), fn.get("arguments")
        args, problem, kind = validate_call(name, raw)
        if not problem:
            problem = grounding_problem(name, args, seen)
            kind = "malformed_args" if problem else None
        rec = {
            "step": step,
            "name": name,
            "args": args if args is not None else raw,
            "valid": problem is None,
            "problem": problem,
            "category": kind,
        }
        if problem:
            problems.append(f"{name}: {problem}")
            if verbose:
                print(f"  step {step}  model -> {name}({json.dumps(raw)})  REJECTED: {problem}")
        else:
            result = json.loads(execute_tool(name, args, store=store))
            st["tool_calls"] += 1
            rec.update(
                result_ok=result["ok"],
                data=result["data"],
                result_code=result["error"]["code"] if result["error"] else "OK",
            )
            good.append((name, args, result))
            st["seen_codes"].update(CODE_FIND.findall(json.dumps(result, default=str)))
            if verbose:
                print(f"  step {step}  model -> {name}({json.dumps(args)})\n           tool  <- {short(result)}")
        st["calls"].append(rec)
        log_event(st.get("log_path"), {"run_id": run_id, "event": "tool_call", **rec})
    if good:  # echo only well-formed calls back, each followed by its tool-role result
        st["messages"].append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a, _ in good],
            }
        )
        for n, _, r in good:
            st["messages"].append({"role": "tool", "content": json.dumps(r, default=str), "tool_name": n})
    return problems


def handle_reply(st: dict, step: int, reply: dict, store, run_id: str, verbose: bool) -> bool:
    calls = reply.get("tool_calls") or []
    if not calls and st["tool_calls"] == 0 and not st["calls"]:  # text where a tool call was required
        st["calls"].append(
            {
                "step": step,
                "name": None,
                "args": None,
                "valid": False,
                "category": "text_instead_of_tool",
                "problem": "answered in text before calling any tool",
            }
        )
        problems = ["you answered in text, but this question needs data from the tools; call a tool first"]
        if verbose:
            print(f"  step {step}  model -> text without a tool call  REJECTED (tool required)")
    elif not calls and incomplete(reply.get("text", "")) and not st["nudged"]:
        st["nudged"], st["repairs"] = True, st["repairs"] + 1  # one nudge only, so the loop stays bounded
        st["messages"].append({"role": "assistant", "content": reply.get("text", "")})
        st["messages"].append({"role": "user", "content": INCOMPLETE_PROMPT})
        if verbose:
            print(f"  step {step}  model -> unfinished answer  NUDGED (call the tool still needed)")
        return False
    elif not calls:
        st["answer"], st["stop_reason"] = reply.get("text", "").strip(), "final_answer"
        if verbose:
            print(f"  step {step}  model -> final answer")
        return True
    else:
        problems = run_calls(st, step, calls, store, run_id, verbose)
    if problems:
        st["failed_streak"] += 1
        if st["failed_streak"] > MAX_FAILED_REPAIRS:
            st["stop_reason"] = "repair_failed"
            st["answer"] = f"Stopped: the model could not produce a valid tool call ({problems[-1]})."
            return True
        st["repairs"] += 1
        st["messages"].append({"role": "user", "content": repair_prompt(problems)})
    else:
        st["failed_streak"] = 0
    return False


def run_agent(
    user_input: str,
    model=None,
    store=None,
    verbose: bool = True,
    log_path: Path | None = LOG_PATH,
    context_note: str | None = None,
    max_iters: int = MAX_ITERS,
    max_tool_calls: int | None = None,
    token_budget: int | None = None,
) -> dict:
    model = model or LocalModel()
    run_id, start = uuid.uuid4().hex[:8], time.perf_counter()
    st = new_state(user_input, context_note)
    st["log_path"] = log_path
    log_event(log_path, {"run_id": run_id, "event": "start", "model": model.name, "user_input": user_input})
    if verbose:
        print(f"[run {run_id}] {user_input}")
    step = 0
    while step < max_iters:
        step += 1
        if max_tool_calls is not None and st["tool_calls"] >= max_tool_calls:
            st["stop_reason"] = "budget_exhausted"
            break
        if token_budget is not None and st["tokens_in"] + st["tokens_out"] >= token_budget:
            st["stop_reason"] = "budget_exhausted"
            break
        try:
            reply = model.chat(st["messages"])
        except Exception as exc:  # model server down: stop cleanly instead of crashing
            st["answer"], st["stop_reason"] = f"model error: {exc}", "model_error"
            break
        st["tokens_in"] += reply.get("input_tokens", 0)
        st["tokens_out"] += reply.get("output_tokens", 0)
        if handle_reply(st, step, reply, store, run_id, verbose):
            break
    if st["stop_reason"] in ("max_iters", "budget_exhausted") and not st["answer"]:
        st["answer"] = f"Stopped ({st['stop_reason']}) after {st['tool_calls']} tool call(s) without a final answer."
    out = {
        "run_id": run_id,
        "input": user_input,
        "answer": st["answer"],
        "stop_reason": st["stop_reason"],
        "iterations": step,
        "tool_calls": st["tool_calls"],
        "repairs": st["repairs"],
        "calls": st["calls"],
        "tokens_in": st["tokens_in"],
        "tokens_out": st["tokens_out"],
        "latency_ms": round((time.perf_counter() - start) * 1000),
    }
    log_event(log_path, {"run_id": run_id, "event": "stop", **{k: v for k, v in out.items() if k != "calls"}})
    if verbose:
        print(f"answer: {out['answer']}")
        print(
            f"stop={out['stop_reason']}  iterations={step}  tool_calls={out['tool_calls']}  repairs={out['repairs']}"
            f"  tokens={out['tokens_in'] + out['tokens_out']}  latency={out['latency_ms']} ms"
        )
    return out


if __name__ == "__main__":
    from hw7_tasks import TASKS, check, save_cases

    save_cases()
    arg = " ".join(sys.argv[1:]) or "A"
    task_id = arg.upper() if arg.upper() in TASKS else None
    print(f"=== HW7 Part 2 agent | model {MODEL_NAME} temp 0 seed {SEED} | {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    if task_id:
        print(f"Task {task_id} ({TASKS[task_id]['kind']})")
    result = run_agent(TASKS[task_id]["prompt"] if task_id else arg)
    if task_id:
        passed, why = check(task_id, result)
        print(f"check: {'PASS' if passed else 'FAIL'} - {why}")
