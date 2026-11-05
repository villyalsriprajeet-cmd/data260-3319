# HW9 Step 0: check Redis (with vector search), MySQL s3319_rel, Ollama, Kafka and the embedder
# usage (repo root): python -m code.hw9.check_setup
import asyncio
import json
import os
import urllib.request

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from code.kafka_service.settings import PREFIX, banner

import redis
from sqlalchemy import text

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
RESULTS = []


def show(name, ok, detail):
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:<34} {detail}", flush=True)


def check_redis():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=5)
    show("Redis ping", r.ping(), f"{REDIS_HOST}:{REDIS_PORT}, server {r.info('server')['redis_version']}")
    modules = {m["name"] for m in r.module_list()}
    show("Redis vector search module", "search" in modules, f"modules: {sorted(modules)}")
    others = [k for k in r.scan_iter(count=1000) if not k.startswith(f"{PREFIX}:")]
    show(f"All Redis keys start with {PREFIX}:", not others, f"{r.dbsize()} keys, {len(others)} without prefix")


def check_mysql():
    from code.api.database import engine

    with engine.connect() as conn:
        db = conn.execute(text("SELECT DATABASE()")).scalar()
        fixtures = conn.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
        teams = conn.execute(text("SELECT COUNT(*) FROM teams")).scalar()
        row = conn.execute(
            text("SELECT id, fixture_code, venue, tickets_available, updated_at FROM fixtures ORDER BY id LIMIT 1")
        ).one()
    show("MySQL connection", db == f"{PREFIX}_rel", f"database {db}")
    show("MySQL fixtures and teams rows", fixtures > 0 and teams > 0, f"{fixtures} fixtures, {teams} teams")
    show("MySQL sample fixture", True, dict(row._mapping))


def check_ollama():
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=10) as resp:
        models = [m["name"] for m in json.loads(resp.read())["models"]]
    show("Ollama qwen2.5:3b pulled", "qwen2.5:3b" in models, f"models: {models}")


async def kafka_topics():
    from aiokafka.admin import AIOKafkaAdminClient

    admin = AIOKafkaAdminClient(bootstrap_servers="localhost:9092", request_timeout_ms=10000)
    await admin.start()
    try:
        return sorted(t for t in await admin.list_topics() if t.startswith(PREFIX))
    finally:
        await admin.close()


def check_kafka():
    topics = asyncio.run(kafka_topics())
    need = {f"{PREFIX}_{t}" for t in ("inbox", "tasks", "drafts", "final")}
    show("Kafka HW8 agent topics", need <= set(topics), f"topics: {topics}")


def check_embedder():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    vec = model.encode(["How many tickets are left for FX-00042?"], normalize_embeddings=True)[0]
    show("Embedder all-MiniLM-L6-v2", len(vec) == 384, f"dimension {len(vec)}")


if __name__ == "__main__":
    banner("HW9 Step 0 setup check")
    for name, fn in [
        ("Redis", check_redis),
        ("MySQL", check_mysql),
        ("Ollama", check_ollama),
        ("Kafka", check_kafka),
        ("Embedder", check_embedder),
    ]:
        try:
            fn()
        except Exception as exc:  # report and keep checking the rest
            show(name, False, f"{type(exc).__name__}: {exc}")
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed", flush=True)
