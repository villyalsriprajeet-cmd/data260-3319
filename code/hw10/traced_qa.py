# HW10 Part 4.1: HW9 fixture Q&A with one trace_id (the correlation_id) from the cache lookup to the evaluator
import time
import uuid
from code.hw9.qa_service import FACTS_SQL, FixtureQA, facts_text, fixture_codes, version_of
from code.hw9.semantic_cache import normalize
from code.hw10.tracing import now_iso, write_span
from code.kafka_service.settings import PREFIX, format_line
from pathlib import Path

from aiokafka import AIOKafkaConsumer, TopicPartition

ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = ROOT / "reports" / "hw10" / "logs" / "qa.log"
EVALUATIONS = f"{PREFIX}_evaluations"
THRESHOLD = 0.95  # the threshold chosen to ship in HW9 Part 3


def tlog(event, cid=None, **fields):
    line = format_line("QA", event, cid, **fields)
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as fh:
        fh.write(line + "\n")


async def tail_many(k, topics):
    producer = await k.make_producer()
    tps = [TopicPartition(t, p) for t in topics for p in sorted(await producer.partitions_for(t))]
    await producer.stop()
    consumer = AIOKafkaConsumer(bootstrap_servers=k.KAFKA_BOOTSTRAP, group_id=None, enable_auto_commit=False)
    await consumer.start()
    consumer.assign(tps)
    await consumer.seek_to_end(*tps)  # only messages that arrive from now on
    for tp in tps:
        await consumer.position(tp)
    return consumer


def failing_stage(dead):
    return str(dead.get("failed_agent", "unknown")).split("-")[0].lower()  # WRITER-A becomes writer


class TracedQA(FixtureQA):
    def __init__(self, threshold=THRESHOLD, cache=None, engine=None):
        super().__init__(threshold=threshold, check_version=False, cache=cache, engine=engine)

    async def start(self):
        self.cache.embed_fn("warm up")  # load the embedding model before the first timed lookup
        from code.kafka_agents import common as k  # HW8 helpers and topic names

        self.k = k
        self.consumer = await tail_many(k, [k.FINAL, k.DEAD_LETTER, EVALUATIONS])  # listen before sending
        self.producer = await k.make_producer()

    def timed_lookup(self, cid, query):
        start, t0 = now_iso(), time.perf_counter()
        vector = self.cache.embed_fn(query)
        t1 = time.perf_counter()
        hit, best, vector = self.cache.lookup(query, vector)
        t2 = time.perf_counter()
        sim = round(best["similarity"], 4) if best else None
        info = {"result": "hit" if hit else "miss", "similarity": sim, "threshold": self.cache.threshold}
        info.update({"embed_ms": round((t1 - t0) * 1000, 1), "search_ms": round((t2 - t1) * 1000, 1)})
        info["matched_query"] = best["query"] if best else None
        write_span(cid, "cache_lookup", start, now_iso(), service="qa", **info)
        return hit, best, vector, info

    async def send_question(self, cid, question, fault):
        trace = {"trace_id": cid, "source": "hw10", "asked_at": now_iso()}
        if fault:
            trace["inject_fault"] = fault  # read by runtime.py of that agent
        message = {"correlation_id": cid, "question": question, "trace": trace}
        meta = await self.producer.send_and_wait(self.k.INBOX, self.k.encode(message), key=cid.encode())
        tlog("SENT_TO_AGENTS", cid, topic=meta.topic, partition=meta.partition, offset=meta.offset, fault=fault)

    async def wait_outcome(self, cid, wait_eval, timeout):
        got = {"final": None, "evaluation": None, "dead_letter": None, "error": None}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            batch = await self.consumer.getmany(timeout_ms=500)
            for msg in [m for msgs in batch.values() for m in msgs]:
                record = self.k.decode(msg.value)
                if not record or record.get("correlation_id") != cid:
                    continue
                if msg.topic == self.k.DEAD_LETTER:
                    got["dead_letter"] = record
                    got["error"] = f"{failing_stage(record)}: {record.get('error')}"
                    return got
                if msg.topic == self.k.FINAL:
                    got["final"] = record
                if msg.topic == EVALUATIONS:
                    got["evaluation"] = record
                    if record.get("status") != "ok":
                        got["error"] = f"evaluation: {record.get('error')}"
                if got["final"] and (got["evaluation"] or not wait_eval):
                    return got
        waited = "evaluation" if got["final"] else "final"
        got["error"] = f"timeout after {timeout:.0f} s waiting for the {waited} message"
        return got

    def outcome_stage(self, got):
        if got["dead_letter"]:
            return failing_stage(got["dead_letter"])
        if got["error"]:
            return "evaluation" if got["final"] else "final"
        return None

    async def ask(self, query, wait_eval=True, fault=None, timeout=900, store=True):
        cid, req_start = str(uuid.uuid4()), now_iso()  # the one id for the whole request
        query = normalize(query)
        hit, best, vector, info = self.timed_lookup(cid, query)
        if hit:
            tlog("CACHE_HIT", cid, similarity=info["similarity"], matched_query=info["matched_query"])
            span = write_span(cid, "request", req_start, now_iso(), service="qa", path="hit", query=query)
            return {"trace_id": cid, "path": "hit", "answer": best["answer"], "lookup": info, "request": span}
        tlog("CACHE_MISS", cid, best_similarity=info["similarity"], threshold=info["threshold"], query=query)
        codes = fixture_codes(query)
        rows = self.load_rows(FACTS_SQL, codes)  # MySQL facts, empty when the question has no fixture code
        await self.send_question(cid, query + facts_text(codes, rows), fault)
        got = await self.wait_outcome(cid, wait_eval, timeout)
        answer = str((got["final"] or {}).get("answer", "")).strip()
        if store and answer and not got["dead_letter"]:
            self.cache.store(query, vector, answer, version_of(codes, rows), codes, correlation_id=cid)
        status = "error" if got["error"] else "ok"
        attrs = {"path": "miss", "query": query, "failing_stage": self.outcome_stage(got), "answer": answer}
        span = write_span(cid, "request", req_start, now_iso(), status, got["error"], service="qa", **attrs)
        tlog("REQUEST_DONE", cid, status=status, error=got["error"], ms=span["duration_ms"])
        return {"trace_id": cid, "path": "miss", "answer": answer, "lookup": info, "request": span, **got}
