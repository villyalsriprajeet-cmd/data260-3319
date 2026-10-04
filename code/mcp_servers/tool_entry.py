# HW5 Part 4: execute_tool, the single safe entry point the Part 5 agent uses to call the three domain tools (Part 5 adds the safety rule)
import asyncio
import inspect
import json
import league_server as ls
from envelope import fail
TOOLS = {"search_fixtures": ls.search_fixtures, "fixture_details": ls.fixture_details, "tickets_by_city": ls.tickets_by_city}
MAX_AGENT_RESULTS = 20  # Part 5 safety rule: the assistant may not pull more than 20 fixtures in one call
WILDCARDS = "%_"  
def check_arguments(func, inputs: dict) -> str | None:
    """Return a problem with the argument names or types, or None when they are fine."""
    params = inspect.signature(func).parameters
    unknown = sorted(set(inputs) - set(params))
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    missing = [n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in inputs]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    for name, value in inputs.items():
        expected = params[name].annotation
        if expected in (int, str) and (not isinstance(value, expected) or isinstance(value, bool)):
            return f"{name} must be {expected.__name__}, got {type(value).__name__}"
    return None
def safety_check(name: str, inputs: dict) -> str | None:
    """Part 5 business rule: no bulk export of fixture data through the assistant."""
    if name == "search_fixtures":
        if inputs.get("limit", 10) > MAX_AGENT_RESULTS:
            return f"blocked by safety rule: at most {MAX_AGENT_RESULTS} fixtures per search, asked for {inputs['limit']}"
        if any(ch in inputs.get("query", "") for ch in WILDCARDS):
            return "blocked by safety rule: wildcard characters (% or _) are not allowed in a search"
    return None
def execute_tool(name: str, inputs: dict | None = None, store=None) -> str:
    """Run one domain tool and always return a JSON string in the {ok, data, error} envelope."""
    previous = ls._store
    if store is not None:
        ls._store = store  # dependency injection: tests pass a fake store, so no database is needed
    try:
        if name not in TOOLS:
            result = fail("UNKNOWN_TOOL", f"unknown tool '{name}'; available: {', '.join(TOOLS)}")
        elif not isinstance(inputs if inputs is not None else {}, dict):
            result = fail("INVALID_INPUT", "inputs must be a JSON object")
        else:
            inputs = inputs or {}
            problem = check_arguments(TOOLS[name], inputs)
            blocked = None if problem else safety_check(name, inputs)
            if problem:
                result = fail("INVALID_INPUT", problem)
            elif blocked:
                result = fail("SAFETY_BLOCKED", blocked)  # rule broken: clean envelope, no exception
            else:
                result = asyncio.run(TOOLS[name](**inputs))
    except Exception as exc:  # last safety net: never crash the caller
        result = fail("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")
    finally:
        ls._store = previous
    return json.dumps(result, default=str)