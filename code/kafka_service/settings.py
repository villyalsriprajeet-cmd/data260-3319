# HW8 settings: config values, topic names and logging
import json
import os
from datetime import datetime, timezone

SID4 = 3319
PORT_BASE = 8000 + SID4 % 900  # 8619
PREFIX = f"s{SID4}"
SEED = SID4
VERIFY_SEED = 260000 + SID4  # 263319
DOMAIN_ID = SID4 % 8  # 7, sports league fixtures
STUDENT_NAME = os.getenv("STUDENT_NAME", "Sri Prajeet Villyal")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
REQUEST_TOPIC = f"{PREFIX}_fixture_requests"  # requests go here
RESPONSE_TOPIC = f"{PREFIX}_fixture_responses"  # replies go here
WORKER_GROUP = f"{PREFIX}_fixture_worker_group"
RPC_TIMEOUT_SECONDS = float(os.getenv("RPC_TIMEOUT_SECONDS", "10"))


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def format_line(role, event, cid=None, **fields):
    parts = [now_utc(), f"[{role}]", event]
    if cid is not None:
        parts.append(f"correlation_id={cid}")
    for key, value in fields.items():
        text = json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value
        parts.append(f"{key}={text}")
    return " ".join(str(p) for p in parts)  # one line per event


def log(role, event, cid=None, **fields):
    line = format_line(role, event, cid, **fields)
    print(line, flush=True)
    return line


def banner(script):
    line = f"{STUDENT_NAME} (SID4 {SID4}, prefix {PREFIX}, port {PORT_BASE}) - {script}"
    print(line, flush=True)
