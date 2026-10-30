# HW8 Part 1 demo: create a fixture, then read it back
# run from the repo root: python code/homework_demo.py
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code" / "kafka_service"))
from settings import PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC, banner, now_utc

API_URL = f"http://127.0.0.1:{PORT_BASE}/fixtures/kafka"
CONTAINERS = ("s3319_api", "s3319_worker")
RAW_DIR = ROOT / "reports" / "hw08" / "raw"
LOG_DIR = ROOT / "reports" / "hw08" / "logs"
STAGES = [
    ("[CLIENT] SENDING_HTTP_REQUEST", "client creates the request with its correlation_id"),
    ("[API] HTTP_REQUEST_RECEIVED", "FastAPI receives the HTTP call"),
    ("[API] SENT_REQUEST", f"FastAPI sends the message to {REQUEST_TOPIC}"),
    ("[WORKER] RECEIVED", f"worker receives it from {REQUEST_TOPIC}"),
    ("[WORKER] PROCESSED", "worker validates and processes it"),
    ("[WORKER] SENT_RESPONSE", "worker sends the reply to the reply_to topic"),
    ("[WORKER] OFFSET_COMMITTED", "worker commits the offset after replying"),
    ("[API] RECEIVED_RESPONSE", f"FastAPI receives the reply from {RESPONSE_TOPIC}"),
    ("[API] RETURNING_HTTP_RESPONSE", "FastAPI returns the reply to the caller"),
    ("[CLIENT] RECEIVED_RESPONSE", "client receives the final response"),
]
EVENT_ORDER = {
    "HTTP_REQUEST_RECEIVED": 0,
    "SENT_REQUEST": 1,
    "RECEIVED": 2,
    "PROCESSED": 3,
    "SENT_RESPONSE": 4,
    "OFFSET_COMMITTED": 5,
    "RECEIVED_RESPONSE": 6,
    "MATCHED_PENDING_REQUEST": 7,
    "RETURNING_HTTP_RESPONSE": 8,
}


def client_line(event, cid, payload):
    return f"{now_utc()} [CLIENT] {event} correlation_id={cid} body={json.dumps(payload, separators=(',', ':'))}"


def container_lines(since, cid):
    lines = []
    for name in CONTAINERS:
        out = subprocess.run(["docker", "logs", "--since", since, name], capture_output=True, text=True)
        lines += [ln for ln in (out.stdout + out.stderr).splitlines() if f"correlation_id={cid}" in ln]
    return sorted(lines, key=lambda ln: (ln[:24], EVENT_ORDER.get(ln.split()[2], 99)))


def call(operation, data, since):
    cid = str(uuid.uuid4())  # made once by the client
    body = {"correlation_id": cid, "operation": operation, "data": data}
    sent = client_line("SENDING_HTTP_REQUEST", cid, body)
    print(sent)
    response = requests.post(API_URL, json=body, timeout=30).json()
    got = client_line("RECEIVED_RESPONSE", cid, response)
    print(got)
    time.sleep(0.5)  # give docker time to write the logs
    lines = container_lines(since, cid)
    cut = next((i + 1 for i, ln in enumerate(lines) if "RETURNING_HTTP_RESPONSE" in ln), len(lines))
    sequence = [sent] + lines[:cut] + [got] + lines[cut:]  # client gets the reply right after the API returns it
    return cid, response, sequence


def show_sequence(title, sequence):
    print(f"\n{title} message sequence (send, receive, process, reply, client):")
    for line in sequence:
        print(line)
    print(f"\n{title} stage check:")
    for tag, meaning in STAGES:
        print(f"  [{'OK' if any(tag in ln for ln in sequence) else 'MISSING'}] {tag:<32} {meaning}")


def check_preserved(cid, response, sequence):
    in_response = response.get("correlation_id") == cid
    in_logs = all(f"correlation_id={cid}" in ln for ln in sequence)
    print(f"  correlation_id sent      : {cid}")
    print(f"  correlation_id returned  : {response.get('correlation_id')}")
    print(f"  preserved in response    : {in_response}")
    print(f"  same id on all {len(sequence)} log lines: {in_logs}")
    return in_response and in_logs


def error_cases(since, fixture):
    cases = [
        ("unknown operation", "DELETE_EVERYTHING", {}),
        ("missing field (venue)", "CREATE_FIXTURE", {k: v for k, v in fixture.items() if k != "venue"}),
        ("invalid fixture_code", "CREATE_FIXTURE", {**fixture, "fixture_code": "BAD-1"}),
        ("empty fixture_title", "CREATE_FIXTURE", {**fixture, "fixture_title": "   ", "fixture_code": "FX-00000"}),
        ("unknown fixture_id", "GET_FIXTURE", {"fixture_id": str(uuid.uuid4())}),
    ]
    results = []
    print("\nExtra: validation and error responses (each keeps its correlation_id)")
    for label, operation, data in cases:
        cid, response, _ = call(operation, data, since)
        ok = response.get("success") is False and response.get("correlation_id") == cid and response.get("error")
        error = repr(response.get("error"))
        print(f"  -> {label}: success={response.get('success')} error={error} cid_kept={bool(ok)}\n")
        results.append({"case": label, "correlation_id": cid, "response": response, "passed": bool(ok)})
    return results


def save(result, sequences):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "p1_demo_result.json").write_text(json.dumps(result, indent=2) + "\n")
    (LOG_DIR / "p1_demo_sequence.log").write_text("\n".join(sequences) + "\n")
    print("\nSaved reports/hw08/raw/p1_demo_result.json and reports/hw08/logs/p1_demo_sequence.log")


def new_fixture():
    return {
        "fixture_title": "Spartans vs Eagles - Matchweek 9",
        "fixture_code": f"FX-{int(time.time()) % 100000:05d}",  # new code each run
        "venue": "Riverside Park",
        "tickets_available": 250,
        "home_team_id": 1,
    }


def step_ten(fixture, create, get):
    print("\nStep 10: retrieved fixture and correlation_id check")
    print(json.dumps(get[1].get("fixture"), indent=2))
    same = {k: v for k, v in (get[1].get("fixture") or {}).items() if k != "fixture_id"} == fixture
    print(f"  retrieved fields match what was created: {same}")
    print("CREATE_FIXTURE:")
    ok_c = check_preserved(*create)
    print("GET_FIXTURE:")
    ok_g = check_preserved(*get)
    return bool(create[1].get("success") and get[1].get("success") and same and ok_c and ok_g)


def main():
    banner("Part 1 homework_demo.py")
    since = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(requests.get(API_URL.rsplit("/fixtures", 1)[0] + "/", timeout=10).json())
    fixture = new_fixture()
    print("\nSteps 1-6: CREATE_FIXTURE")
    create = call("CREATE_FIXTURE", fixture, since)
    show_sequence("CREATE_FIXTURE", create[2])
    fixture_id = create[1].get("fixture_id")  # id made by the worker
    print(f"\nStep 7: generated fixture_id = {fixture_id}")
    print("\nSteps 8-9: GET_FIXTURE")
    get = call("GET_FIXTURE", {"fixture_id": fixture_id}, since)
    show_sequence("GET_FIXTURE", get[2])
    passed = step_ten(fixture, create, get)
    errors = error_cases(since, fixture)
    result = {
        "create": {"correlation_id": create[0], "request_data": fixture, "response": create[1]},
        "get": {"correlation_id": get[0], "response": get[1]},
        "error_cases": errors,
        "round_trip_passed": passed,
    }
    save(result, create[2] + [""] + get[2])
    ok = sum(e["passed"] for e in errors)
    print(f"\nRESULT: CREATE -> GET round trip {'PASSED' if passed else 'FAILED'}; {ok}/{len(errors)} clean errors")
    banner("end of homework_demo.py")


if __name__ == "__main__":
    main()
