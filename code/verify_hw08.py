# HW8 self-check: smoke test that writes reports/hw08/verification.json
# usage: make verify-hw08 (docker stack and the agents running)
import argparse
import asyncio
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code" / "kafka_service"))
sys.path.insert(0, str(ROOT / "code" / "kafka_agents"))
from settings import DOMAIN_ID, PORT_BASE, PREFIX, SEED, SID4, VERIFY_SEED, banner

REPORT_DIR = ROOT / "reports" / "hw08"
RAW_DIR = REPORT_DIR / "raw"
LOG_DIR = REPORT_DIR / "logs"
API = f"http://127.0.0.1:{PORT_BASE}"
CONFIG = {
    "SID4": SID4,
    "PORT_BASE": PORT_BASE,
    "PREFIX": PREFIX,
    "SEED": SEED,
    "VERIFY_SEED": VERIFY_SEED,
    "DOMAIN_ID": DOMAIN_ID,
}
TOPICS = {
    "fixture_requests": 1,
    "fixture_responses": 1,
    "inbox": 1,
    "tasks": 2,
    "drafts": 1,
    "final": 1,
    "dead_letter": 1,
}
MODEL = {
    "llm": "qwen2.5:3b",
    "runtime": "Ollama (local)",
    "temperature": 0,
    "seed": SEED,
    "kafka": "apache/kafka:3.9.2 (KRaft, single broker)",
    "client": "aiokafka 0.12.0",
}
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
    print("PASS" if ok else "FAIL", name, f"({detail})" if detail != "" else "", flush=True)


def safe(name, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # one broken area must not stop the other checks
        check(name, False, f"{type(exc).__name__}: {exc}")


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def infra():
    running = run("docker", "ps", "--format", "{{.Names}}").split()
    need = [f"{PREFIX}_kafka", f"{PREFIX}_worker", f"{PREFIX}_api"]
    check("docker: kafka, worker and api containers running", all(n in running for n in need), running)
    for name, parts in TOPICS.items():
        topic = f"{PREFIX}_{name}"
        out = run(
            "docker",
            "exec",
            f"{PREFIX}_kafka",
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "kafka:19092",
            "--describe",
            "--topic",
            topic,
        )
        found = re.search(r"PartitionCount:\s*(\d+)", out)
        got = int(found.group(1)) if found else 0
        check(f"topic {topic} exists with {parts} partition(s)", got == parts, f"found {got}")


def post(operation, data, cid=None):
    cid = cid or str(uuid.uuid4())
    body = {"correlation_id": cid, "operation": operation, "data": data}
    return cid, requests.post(f"{API}/fixtures/kafka", json=body, timeout=30).json()


def part1_api():
    home = requests.get(f"{API}/", timeout=10).json()
    topics = (home.get("request_topic"), home.get("response_topic"))
    check(
        "API on PORT_BASE names the two prefixed topics",
        topics == (f"{PREFIX}_fixture_requests", f"{PREFIX}_fixture_responses"),
        topics,
    )
    data = {
        "fixture_title": "verify-hw08 fixture",
        "fixture_code": f"FX-{uuid.uuid4().int % 100000:05d}",
        "venue": "Verify Field",
        "tickets_available": 10,
        "home_team_id": 1,
    }
    cid, made = post("CREATE_FIXTURE", data)
    fid = made.get("fixture_id", "")
    ok = made.get("success") and UUID4.match(fid) and made.get("correlation_id") == cid
    check("CREATE_FIXTURE returns success, a UUID fixture_id and the same correlation_id", ok, made)
    gcid, got = post("GET_FIXTURE", {"fixture_id": fid})
    same = {k: v for k, v in (got.get("fixture") or {}).items() if k != "fixture_id"} == data
    check(
        "GET_FIXTURE returns the created fixture and the same correlation_id",
        got.get("success") and same and got.get("correlation_id") == gcid,
        got,
    )
    _, again = post("CREATE_FIXTURE", data, cid)
    check(
        "CREATE replayed with the same correlation_id gives the same fixture_id",
        again.get("fixture_id") == fid and again.get("duplicate") is True,
        again,
    )
    errors(data)


def errors(data):
    cases = [
        ("unknown operation", "RENAME_FIXTURE", {}, "Unknown operation"),
        ("missing field", "CREATE_FIXTURE", {k: v for k, v in data.items() if k != "venue"}, "venue"),
        ("invalid value", "CREATE_FIXTURE", {**data, "tickets_available": -5}, "tickets_available"),
        ("unknown fixture_id", "GET_FIXTURE", {"fixture_id": str(uuid.uuid4())}, "Fixture not found"),
    ]
    for label, op, body, want in cases:
        cid, out = post(op, body)
        ok = out.get("success") is False and want in str(out.get("error")) and out.get("correlation_id") == cid
        check(
            f"error case ({label}) gives success false, a clean error and the same correlation_id", ok, out.get("error")
        )


async def direct_kafka():
    from common import encode, make_producer, tail_consumer

    consumer = await tail_consumer(f"{PREFIX}_fixture_responses")
    cid = f"verify-direct-{uuid.uuid4()}"
    msg = {
        "correlation_id": cid,
        "reply_to": f"{PREFIX}_fixture_responses",
        "operation": "GET_FIXTURE",
        "data": {"fixture_id": "does-not-exist"},
    }
    producer = await make_producer()
    await producer.send_and_wait(f"{PREFIX}_fixture_requests", encode(msg), key=cid.encode())
    await producer.stop()
    try:
        reply = await asyncio.wait_for(find_reply(consumer, cid), timeout=20)
    finally:
        await consumer.stop()
    ok = reply.get("correlation_id") == cid and reply.get("success") is False
    check("raw Kafka: request topic to worker to reply_to topic keeps the correlation_id", ok, reply)


async def find_reply(consumer, cid):
    async for m in consumer:
        value = json.loads(m.value)
        if value.get("correlation_id") == cid:
            return value


async def pipeline():
    from common import encode, make_producer, tail_consumer
    from send_question import QUESTION, wait_for_final

    consumer = await tail_consumer(f"{PREFIX}_final")
    cid = str(uuid.uuid4())
    producer = await make_producer()
    body = encode({"correlation_id": cid, "question": QUESTION})
    await producer.send_and_wait(f"{PREFIX}_inbox", body, key=cid.encode())
    await producer.stop()
    try:
        final = await wait_for_final(consumer, cid, 600)
    finally:
        await consumer.stop()
    ok = final.get("correlation_id") == cid and final.get("status") in ("approved", "needs_revision")
    check(
        "Part 2 live: inbox, Planner, Writer, Reviewer, final with one correlation_id",
        ok and final.get("answer"),
        final.get("status"),
    )


def load(name):
    return json.loads((RAW_DIR / name).read_text())


def ordering(run_name):
    summary = load(f"ordering_{run_name}_summary.json")
    entities = summary["entities"].values()
    writers = {w for e in entities for w in e["writers"]}
    parts = {p for e in entities for p in e["partitions"]}
    split = sum(len(e["partitions"]) > 1 for e in entities)
    return summary, writers, parts, split


def evidence():
    check("Part 1 saved demo: CREATE then GET round trip passed", load("p1_demo_result.json").get("round_trip_passed"))
    final = load("p2_final_message.json")
    check(
        "Part 2 saved final JSON has correlation_id, status and answer",
        all(final.get(k) for k in ("correlation_id", "status", "answer")),
        final.get("status"),
    )
    drafts = load("p3_dup_after_drafts.json")
    check(
        "Part 3 duplicate: still 2 drafts after both replays (bug run 1 extra, fixed run 0)",
        len(drafts) == 2,
        len(drafts),
    )
    dead = load("p3_dead_letter.json")
    ok = any(d["value"].get("attempts") == 3 and d["value"].get("source_topic") == f"{PREFIX}_tasks" for d in dead)
    check("Part 3 poison: dead letter entry after 3 attempts", ok, len(dead))
    nokey, writers, _, split = ordering("nokey")
    ok = nokey["messages_processed"] == 20 and split > 0 and len(writers) == 2
    check(
        "Part 3 ordering no key: 20 processed by 2 Writers, fixtures split",
        ok,
        f"{split}/4 split, {nokey['entities_in_order']}/4 in order",
    )
    keyed, writers, parts, _ = ordering("keyed")
    ok = (
        keyed["messages_processed"] == 20
        and keyed["entities_in_one_partition"] == 4
        and keyed["entities_in_order"] == 4
    )
    check(
        "Part 3 ordering keyed: 4/4 in one partition and in order, 2 Writers",
        ok and parts == {0, 1} and len(writers) == 2,
        sorted(writers),
    )
    text = (LOG_DIR / "agents.log").read_text()
    for event in ("DUPLICATE_SKIPPED", "REDELIVERED", "MOVED_TO_DEAD_LETTER", "PARTITIONS_ASSIGNED"):
        check(f"Part 3 logs contain {event}", event in text)


def offline():
    from fixture_store import process_request

    store = {}
    base = {"correlation_id": "c", "reply_to": f"{PREFIX}_fixture_responses"}
    bad = process_request({**base, "operation": "CREATE_FIXTURE", "data": {"fixture_title": ""}}, store)
    check("offline: validation rejects bad data and stores nothing", not bad["success"] and not store, bad["error"])
    paths = ["code/kafka_service", "code/kafka_agents", "code/homework_demo.py", "code/verify_hw08.py"]
    lint = subprocess.run(["ruff", "check", *paths], cwd=ROOT, capture_output=True, text=True)
    check("ruff passes on the HW8 code", lint.returncode == 0, (lint.stdout.strip().splitlines() or ["ok"])[-1])


def main(args):
    banner("verify_hw08.py")
    print(f"started {datetime.now():%Y-%m-%d %H:%M:%S}\n", flush=True)
    safe("docker containers and topics", infra)
    safe("Part 1 API checks", part1_api)
    safe("raw Kafka contract", lambda: asyncio.run(direct_kafka()))
    if args.with_agents:
        safe("Part 2 live pipeline", lambda: asyncio.run(pipeline()))
    safe("saved evidence", evidence)
    safe("offline checks", offline)
    out = {
        "hw": "hw8",
        "sid4": SID4,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "commit_hash": run("git", "rev-parse", "HEAD") or "unknown",
        "tag": run("git", "tag", "--points-at", "HEAD") or "none",
        "config": CONFIG,
        "model": MODEL,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "all_passed": all(c["passed"] for c in CHECKS),
        "checks": CHECKS,
    }
    (REPORT_DIR / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    passed = sum(c["passed"] for c in CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed, saved reports/hw08/verification.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-agents", action="store_true", help="also send one live question through the agents")
    main(parser.parse_args())
