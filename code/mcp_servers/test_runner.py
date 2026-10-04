# HW5 Parts 4-5: offline test runner for execute_tool and run_agent (no database, no network, no LLM)
import json
import os
import sys
import tempfile
from pathlib import Path
import traceback
os.environ["DATABASE_URL"] = "mysql+pymysql://nobody:nothing@offline.invalid:1/none"  
import league_server as ls
from fake_store import FakeStore
from faults import FaultInjector
from tool_entry import execute_tool
from agent import MockModel, run_agent
ls.RETRY_POLICY = ls.RetryPolicy(max_attempts=3, base_delay=0.001, max_delay=0.01)  # tiny waits so tests stay fast
TESTS = []
def test(func):
    TESTS.append(func)
    return func
def call(name, inputs, store=None):
    """Run execute_tool with a fresh fake store and check the reply is the JSON envelope."""
    raw = execute_tool(name, inputs, store=store or FakeStore())
    assert isinstance(raw, str), "execute_tool must return a JSON string"
    result = json.loads(raw)
    assert set(result) == {"ok", "data", "error"}, f"envelope keys wrong: {set(result)}"
    assert (result["error"] is None) == result["ok"], "error must be null exactly when ok is true"
    return result
@test
def search_fixtures_valid():
    r = call("search_fixtures", {"query": "Hawks", "limit": 3})
    assert r["ok"] and r["data"]["count"] == 2
    assert [f["fixture_code"] for f in r["data"]["results"]] == ["FX-00001", "FX-00002"]
@test
def search_fixtures_rejects_short_query():
    r = call("search_fixtures", {"query": "H", "limit": 3})  
    assert not r["ok"] and r["data"] is None
    assert r["error"] == {"code": "INVALID_INPUT", "message": "query must be at least 2 characters"}
@test
def fixture_details_valid():
    r = call("fixture_details", {"fixture_code": "FX-00001"})
    assert r["ok"] and r["data"]["team_name"] == "Pleasanton Hawks" and r["data"]["tickets_available"] == 37


@test
def fixture_details_rejects_bad_code():
    r = call("fixture_details", {"fixture_code": "ABC"}) 
    assert r["error"] == {"code": "INVALID_INPUT", "message": "fixture_code must look like FX-00001, got 'ABC'"}
@test
def tickets_by_city_valid():
    r = call("tickets_by_city", {"top_n": 2})
    assert r["ok"] and [row["city"] for row in r["data"]] == ["Gilroy", "Santa Clara"]
    assert r["data"][0] == {"city": "Gilroy", "fixtures": 2, "total_tickets": 411, "avg_tickets": 205.5}
@test
def tickets_by_city_rejects_zero():
    r = call("tickets_by_city", {"top_n": 0})  
    assert r["error"] == {"code": "INVALID_INPUT", "message": "top_n must be between 1 and 20, got 0"}
@test
def fixture_details_unknown_code_not_found():
    r = call("fixture_details", {"fixture_code": "FX-99999"})
    assert r["error"]["code"] == "NOT_FOUND"
@test
def unknown_tool_is_rejected():
    r = call("delete_fixture", {"fixture_code": "FX-00001"})
    assert r["error"]["code"] == "UNKNOWN_TOOL"
@test
def wrong_argument_type_and_missing_argument():
    assert call("tickets_by_city", {"top_n": "3"})["error"]["code"] == "INVALID_INPUT"
    assert call("fixture_details", {})["error"]["message"] == "missing required argument(s): fixture_code"
@test
def storage_failure_returns_clean_error():
    store = FakeStore()
    store.fault = FaultInjector(rate=1.0)  # every attempt fails
    r = call("tickets_by_city", {"top_n": 3}, store=store)
    assert r["error"]["code"] == "UNAVAILABLE" and len(store.fault.history) == 3 and store.calls == 0
@test
def safety_rule_blocks_bulk_search():
    store = FakeStore()
    r = call("search_fixtures", {"query": "Field", "limit": 50}, store=store)  # Part 5 rule: max 20 per search
    assert r["error"]["code"] == "SAFETY_BLOCKED" and store.calls == 0  # blocked before the store was touched
    assert call("search_fixtures", {"query": "Field", "limit": 5})["ok"]  # the same search within the limit is allowed
@test
def run_agent_stops_at_max_steps():
    keeps_calling = {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "search_fixtures", "arguments": {"query": "Hawks", "limit": 2}}}]}
    model = MockModel([keeps_calling])  # never gives a final answer
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "agent_runs.jsonl"
        r = run_agent("Find Hawks fixtures", model=model, max_steps=3, store=FakeStore(), log_path=log)
        events = [json.loads(line) for line in log.read_text().splitlines()]
    assert r["stop_reason"] == "max_steps" and r["steps"] == 3 and r["tool_calls"] == 3 and model.calls == 3
    assert events[-1]["event"] == "stop" and events[-1]["stop_reason"] == "max_steps"
def main() -> int:
    passed = 0
    for func in TESTS:
        try:
            func()
            passed += 1
            print(f"PASS  {func.__name__}")
        except AssertionError as exc:
            reason = str(exc) or traceback.extract_tb(exc.__traceback__)[-1].line  # show the failed assert line
            print(f"FAIL  {func.__name__}: {reason}")
        except Exception as exc:
            print(f"FAIL  {func.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1
if __name__ == "__main__":
    sys.exit(main())