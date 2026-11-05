# HW9 Part 2: fixture Q&A endpoint, semantic cache at the ingress, HW8 Kafka agents on a miss
import asyncio
import re
import time
import uuid
from code.hw9.semantic_cache import DEFAULT_THRESHOLD, SemanticCache, normalize
from code.kafka_service.settings import format_line, now_utc
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = ROOT / "reports" / "hw09" / "logs" / "qa_service.log"
CODE_RE = re.compile(r"\bFX-\d{5}\b", re.IGNORECASE)
FACTS_SQL = text(
    "SELECT f.fixture_code, f.fixture_title, f.venue, f.tickets_available, f.updated_at, "
    "t.name AS home_team, t.city AS home_city "
    "FROM fixtures f JOIN teams t ON t.id = f.home_team_id WHERE f.fixture_code IN :codes"
).bindparams(bindparam("codes", expanding=True))
VERSION_SQL = text("SELECT fixture_code, updated_at FROM fixtures WHERE fixture_code IN :codes").bindparams(
    bindparam("codes", expanding=True)
)


def qlog(event, cid=None, **fields):
    line = format_line("QA", event, cid, **fields)
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as fh:
        fh.write(line + "\n")


def fixture_codes(query):
    return sorted({c.upper() for c in CODE_RE.findall(query)})


def version_of(codes, rows):
    if not codes:
        return "none"  # the answer does not depend on a fixture row
    stamp = {r["fixture_code"]: r["updated_at"].isoformat() for r in rows}
    return ";".join(f"{c}@{stamp.get(c, 'missing')}" for c in codes)  # data version marker


def facts_text(codes, rows):
    if not codes:
        return ""
    lines = [
        f'- {r["fixture_code"]}: title "{r["fixture_title"]}", venue {r["venue"]}, '
        f"tickets_available {r['tickets_available']}, home team {r['home_team']} ({r['home_city']})"
        for r in rows
    ]
    found = {r["fixture_code"] for r in rows}
    lines += [f"- {c}: no fixture with this code exists in the league database" for c in codes if c not in found]
    return "\n\nFixture facts from the league database s3319_rel (use these exact values):\n" + "\n".join(lines)


class FixtureQA:
    def __init__(self, threshold=DEFAULT_THRESHOLD, check_version=False, cache=None, engine=None, agents=None):
        self.cache = cache or SemanticCache(threshold=threshold)
        if engine is None:
            from code.api.database import engine  # MySQL s3319_rel
        self.engine = engine
        self.check_version = check_version  # Part 3.5: compare the stored data-version marker on every hit
        self.agents = agents  # None = the real HW8 Kafka pipeline
        self.producer = self.consumer = None

    async def start(self):
        self.cache.embed_fn("warm up")  # load the embedding model once so the first query is not slower
        if self.agents is None:
            from code.kafka_agents import common as k  # HW8 helpers: producer, consumer at the end of s3319_final

            self.k = k
            self.consumer = await k.tail_consumer(k.FINAL)  # listen before sending
            self.producer = await k.make_producer()
            self.agents = self.run_hw8_agents

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def run_hw8_agents(self, question, cid, timeout=900):
        k = self.k
        message = {"correlation_id": cid, "question": question, "trace": {"asked_at": now_utc(), "source": "hw9_qa"}}
        meta = await self.producer.send_and_wait(k.INBOX, k.encode(message), key=cid.encode())
        qlog("SENT_TO_AGENTS", cid, topic=meta.topic, partition=meta.partition, offset=meta.offset)

        async def wait_final():
            while True:
                msg = await self.consumer.getone()
                record = k.decode(msg.value)
                if record and record.get("correlation_id") == cid:
                    return record

        final = await asyncio.wait_for(wait_final(), timeout=timeout)
        qlog("FINAL_FROM_AGENTS", cid, status=final.get("status"), words=len(str(final.get("answer", "")).split()))
        return final

    def load_rows(self, sql, codes):
        if not codes:
            return []
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(sql, {"codes": codes})]

    def current_version(self, codes):
        return version_of(codes, self.load_rows(VERSION_SQL, codes))

    async def handle_query(self, query, use_cache=True):
        started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        t0 = time.perf_counter()
        query = normalize(query)
        vector = self.cache.embed_fn(query)  # step 1: embed the question
        t1 = time.perf_counter()
        hit, best, vector = self.cache.lookup(query, vector)  # step 2: nearest cached question in Redis
        t2 = time.perf_counter()
        embed_ms, search_ms, lookup_ms = (t1 - t0) * 1000, (t2 - t1) * 1000, (t2 - t0) * 1000
        best_sim = round(best["similarity"], 4) if best else None
        if use_cache and hit and self.check_version:
            stored_codes = [c for c in best["fixture_codes"].split(",") if c]
            now_version = self.current_version(stored_codes)
            if now_version != best["data_version"]:  # the record changed after the answer was cached
                self.cache.delete(best["key"])
                qlog("STALE_INVALIDATED", similarity=best_sim, cached=best["data_version"], current=now_version)
                hit = False
        if use_cache and hit:
            latency_ms = (time.perf_counter() - t0) * 1000
            qlog("CACHE_HIT", similarity=best_sim, matched_query=best["query"], latency_ms=round(latency_ms, 1))
            return {
                "query": query,
                "answer": best["answer"],
                "is_cached": True,
                "similarity": best_sim,
                "matched_query": best["query"],
                "data_version": best["data_version"],
                "latency_ms": round(latency_ms, 1),
                "lookup_ms": round(lookup_ms, 1),
                "embed_ms": round(embed_ms, 1),
                "search_ms": round(search_ms, 1),
                "agent_ms": 0.0,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            }
        cid = str(uuid.uuid4())
        qlog("CACHE_MISS", cid, best_similarity=best_sim, threshold=self.cache.threshold, query=query)
        codes = fixture_codes(query)
        rows = self.load_rows(FACTS_SQL, codes)
        version = version_of(codes, rows)
        t_agent = time.perf_counter()
        final = await self.agents(query + facts_text(codes, rows), cid)
        agent_ms = (time.perf_counter() - t_agent) * 1000
        answer = str(final.get("answer", "")).strip()
        if use_cache and answer:
            key = self.cache.store(query, vector, answer, version, codes, correlation_id=cid)
            qlog("CACHE_STORED", cid, key=key, data_version=version)
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "query": query,
            "answer": answer,
            "is_cached": False,
            "similarity": best_sim,
            "matched_query": best["query"] if best else None,
            "data_version": version,
            "latency_ms": round(latency_ms, 1),
            "lookup_ms": round(lookup_ms, 1),
            "embed_ms": round(embed_ms, 1),
            "search_ms": round(search_ms, 1),
            "agent_ms": round(agent_ms, 1),
            "correlation_id": cid,
            "review_status": final.get("status"),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }
