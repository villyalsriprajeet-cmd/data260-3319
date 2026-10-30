# HW8 Parts 2 and 3 shared helpers: topics, logging, LLM, idempotency
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRebalanceListener, TopicPartition

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "code" / "kafka_service"))
from settings import KAFKA_BOOTSTRAP, PREFIX, SEED, VERIFY_SEED, banner, format_line, now_utc

from src.model_client import ModelClient

INBOX = f"{PREFIX}_inbox"
TASKS = f"{PREFIX}_tasks"
DRAFTS = f"{PREFIX}_drafts"
FINAL = f"{PREFIX}_final"
DEAD_LETTER = f"{PREFIX}_dead_letter"
MODEL = "qwen2.5:3b"
MAX_ATTEMPTS = 3  # bounded retries before the dead-letter topic
LOG_DIR = ROOT / "reports" / "hw08" / "logs"
RAW_DIR = ROOT / "reports" / "hw08" / "raw"
STATE_DB = Path(__file__).resolve().parent / "state" / "agents_state.db"
ORDER_SEED = VERIFY_SEED  # the ordering test uses VERIFY_SEED


def write_log(line):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "agents.log", "a") as fh:  # one shared file for every agent
        fh.write(line + "\n")


def alog(role, event, cid=None, **fields):
    line = format_line(role, event, cid, **fields)
    print(line, flush=True)
    write_log(line)
    return line


def show_banner(title):
    banner(title)
    write_log(f"{now_utc()} [START] {title}")  # marks each run in the shared log


def decode(raw):
    try:
        value = json.loads(raw.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def encode(value):
    return json.dumps(value).encode("utf-8")


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def first_text(reply, *keys):
    for key in keys:
        if isinstance(reply.get(key), str) and reply[key].strip():
            return reply[key].strip()
    texts = [v.strip() for v in reply.values() if isinstance(v, str) and v.strip()]
    return max(texts, key=len) if texts else ""  # small models sometimes rename the key


async def ask_llm(system, user):
    client = ModelClient(model=MODEL, temperature=0.0, num_ctx=2048, num_predict=320, seed=SEED)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    result = await asyncio.to_thread(client.complete, messages)  # keeps Kafka heartbeats alive
    return parse_json(result["text"]) or {}, result


class ProcessedStore:
    def __init__(self, path=STATE_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS started (agent TEXT, cid TEXT, at TEXT, PRIMARY KEY (agent, cid))")
        self.db.execute("CREATE TABLE IF NOT EXISTS done (agent TEXT, cid TEXT, at TEXT, PRIMARY KEY (agent, cid))")
        self.db.commit()

    def done_at(self, agent, cid):
        row = self.db.execute("SELECT at FROM done WHERE agent=? AND cid=?", (agent, cid)).fetchone()
        return row[0] if row else None

    def mark_started(self, agent, cid):
        row = self.db.execute("SELECT at FROM started WHERE agent=? AND cid=?", (agent, cid)).fetchone()
        self.db.execute("INSERT OR IGNORE INTO started VALUES (?, ?, ?)", (agent, cid, now_utc()))
        self.db.commit()
        return row[0] if row and not self.done_at(agent, cid) else None  # started before, never finished

    def mark_done(self, agent, cid):
        self.db.execute("INSERT OR IGNORE INTO done VALUES (?, ?, ?)", (agent, cid, now_utc()))
        self.db.commit()


class LogAssignments(ConsumerRebalanceListener):
    def __init__(self, role):
        self.role = role

    async def on_partitions_revoked(self, revoked):
        alog(self.role, "PARTITIONS_REVOKED", partitions=sorted(tp.partition for tp in revoked))

    async def on_partitions_assigned(self, assigned):
        alog(self.role, "PARTITIONS_ASSIGNED", partitions=sorted(tp.partition for tp in assigned))


async def make_producer():
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all")
    await producer.start()
    return producer


async def make_consumer(topic, group, role):
    consumer = AIOKafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,  # offsets are committed by hand
        session_timeout_ms=10000,
        heartbeat_interval_ms=3000,
    )
    await consumer.start()
    consumer.subscribe([topic], listener=LogAssignments(role))
    return consumer


async def tail_consumer(topic):
    producer = await make_producer()
    parts = await producer.partitions_for(topic)
    await producer.stop()
    consumer = AIOKafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, group_id=None, enable_auto_commit=False)
    await consumer.start()
    tps = [TopicPartition(topic, p) for p in sorted(parts)]
    consumer.assign(tps)
    await consumer.seek_to_end(*tps)  # only messages that arrive from now on
    for tp in tps:
        await consumer.position(tp)
    return consumer


async def read_all(topic):
    producer = await make_producer()
    parts = await producer.partitions_for(topic)
    await producer.stop()
    consumer = AIOKafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, group_id=None, enable_auto_commit=False)
    await consumer.start()
    tps = [TopicPartition(topic, p) for p in sorted(parts)]
    consumer.assign(tps)
    await consumer.seek_to_beginning(*tps)
    end = await consumer.end_offsets(tps)
    found = []
    try:
        while True:
            positions = [await consumer.position(tp) for tp in tps]
            if all(pos >= end[tp] for pos, tp in zip(positions, tps)):
                break  # read up to the end offset seen at the start
            batch = await consumer.getmany(timeout_ms=1000)
            found += [m for msgs in batch.values() for m in msgs]
    finally:
        await consumer.stop()
    return sorted(found, key=lambda m: (m.partition, m.offset))


def journey_lines(cid):
    path = LOG_DIR / "agents.log"
    lines = path.read_text().splitlines() if path.exists() else []
    found = [ln for ln in lines if f"correlation_id={cid}" in ln]
    return sorted(found, key=lambda ln: ln[:24])  # by time, ties keep file order
