# HW7 Parts 2: the fixed verification tasks and a deterministic check for each (no model involved)
import json
import re
from pathlib import Path

CASES_PATH = Path(__file__).resolve().parents[1] / "reports" / "hw07" / "cases" / "agent_tasks.json"
TASKS = {
    "A": {
        "kind": "search -> detail lookup",
        "prompt": "Search for fixtures with 'Eagles' in the title, then look up the full details of the first result. "
        "Tell me its fixture code, venue, home team and tickets available.",
    },
    "B": {
        "kind": "aggregate -> supporting example",
        "prompt": "Which home-team city has the most tickets available in total? "
        "Then find one fixture from that city as a supporting example.",
    },
    "C": {
        "kind": "search + two detail lookups -> compare",
        "prompt": "Search for fixtures at 'Gilroy Field', then look up the details of the first two results "
        "and tell me which of the two has more tickets available.",
    },
    "ERR": {
        "kind": "error recovery (nonexistent id)",
        "prompt": "Show me the full details of fixture FX-00000.",
    },
}


def save_cases() -> Path:
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_PATH.write_text(json.dumps(TASKS, indent=2) + "\n")
    return CASES_PATH


def ok_calls(run: dict, name: str) -> list[dict]:
    return [c for c in run["calls"] if c["valid"] and c["name"] == name and c.get("result_ok")]


def has(text: str, value) -> bool:
    return str(value).lower() in (text or "").lower()


def names_fixture(answer: str, row: dict) -> bool:
    teams = row["fixture_title"].split(" - ")[0].split(" vs ")  # "Home Team vs Away Team - Matchweek N"
    both_teams = len(teams) == 2 and all(has(answer, t) for t in teams)
    return has(answer, row["fixture_code"]) or has(answer, row["fixture_title"]) or both_teams


def check_a(run: dict) -> tuple[bool, str]:
    searches = [c for c in ok_calls(run, "search_fixtures") if c["data"]["count"] > 0]
    if not searches:
        return False, "no successful search_fixtures call with results"
    first = searches[0]["data"]["results"][0]["fixture_code"]
    details = [c for c in ok_calls(run, "fixture_details") if c["data"]["fixture_code"] == first]
    if not details:
        return False, f"fixture_details was not called for the first search result {first}"
    d = details[0]["data"]
    if not has(run["answer"], first) or not has(run["answer"], d["tickets_available"]):
        return False, f"answer does not state code {first} and tickets {d['tickets_available']} from the lookup"
    return True, f"searched, looked up first result {first}, answer cites it"


def check_b(run: dict) -> tuple[bool, str]:
    agg = [c for c in ok_calls(run, "tickets_by_city") if c["data"]]
    if not agg:
        return False, "no successful tickets_by_city call"
    city = agg[0]["data"][0]["city"]
    examples = [c for c in ok_calls(run, "search_fixtures") if has(c["args"].get("query", ""), city)]
    if not examples or examples[0]["data"]["count"] == 0:
        return False, f"no search_fixtures call for the top city {city} that returned an example"
    if not has(run["answer"], city):
        return False, f"answer does not name the top city {city}"
    rows = [r for c in examples for r in c["data"]["results"]]
    if not any(names_fixture(run["answer"], r) for r in rows):
        return False, "answer gives no supporting fixture (code, title or both teams) from the search"
    return True, f"top city {city} and a supporting fixture from search"


def check_c(run: dict) -> tuple[bool, str]:
    searches = [c for c in ok_calls(run, "search_fixtures") if c["data"]["count"] >= 2]
    if not searches:
        return False, "no successful search_fixtures call with at least 2 results"
    wanted = [r["fixture_code"] for r in searches[0]["data"]["results"][:2]]
    looked = {c["data"]["fixture_code"]: c["data"] for c in ok_calls(run, "fixture_details")}
    missing = [code for code in wanted if code not in looked]
    if missing:
        return False, f"detail lookups missing for {', '.join(missing)} (needs both of {wanted})"
    a, b = (looked[code] for code in wanted)
    if a["tickets_available"] == b["tickets_available"]:
        return has(run["answer"], "same") or has(run["answer"], "equal"), "tie in tickets"
    winner = a if a["tickets_available"] > b["tickets_available"] else b
    answer = run["answer"] or ""
    if not has(answer, winner["fixture_code"]):
        return False, f"answer does not name the fixture with more tickets ({winner['fixture_code']})"
    claimed = claimed_winner(answer)
    if claimed and claimed != winner["fixture_code"]:
        return False, f"answer says {claimed} has more, but the lookups show {winner['fixture_code']} has more"
    return True, f"compared {wanted}, winner {winner['fixture_code']}"


def claimed_winner(answer: str) -> str | None:
    m = re.search(r"\b(more|most|higher|greater|larger)\b", answer, re.I)
    if not m:
        return None
    codes = re.findall(r"FX-\d{5}", answer[: m.start()].upper())
    return codes[-1] if codes else None  # the fixture named right before "more" is the one claimed to win


def check_err(run: dict) -> tuple[bool, str]:
    nf = [c for c in run["calls"] if c["valid"] and c.get("result_code") == "NOT_FOUND"]
    if not nf:
        return False, "fixture_details was not called or did not return NOT_FOUND"
    if run["stop_reason"] != "final_answer":
        return False, f"agent did not finish cleanly (stop={run['stop_reason']})"
    return True, "tool returned NOT_FOUND and the agent answered without crashing"


CHECKS = {"A": check_a, "B": check_b, "C": check_c, "ERR": check_err}


def check(task_id: str, run: dict) -> tuple[bool, str]:
    return CHECKS[task_id](run)
