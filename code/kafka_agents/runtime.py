# HW8 Parts 2 and 3 consume loop: skip duplicates, retry, dead letter, commit
import argparse
import asyncio
import os

from aiokafka import TopicPartition
from common import (
    DEAD_LETTER,
    MAX_ATTEMPTS,
    ProcessedStore,
    alog,
    decode,
    encode,
    make_consumer,
    make_producer,
    now_utc,
    show_banner,
)


def agent_args(name):
    parser = argparse.ArgumentParser(description=f"{name} agent (HW8)")
    parser.add_argument("--instance", default="", help="label when running two copies, e.g. A or B")
    parser.add_argument(
        "--commit-mode",
        choices=["after", "before"],
        default="after",
        help="after = commit only after success (fix); before = commit on receipt (bug)",
    )
    parser.add_argument("--no-idempotency", action="store_true", help="process replays again (bug)")
    parser.add_argument("--no-dlq", action="store_true", help="retry a failing message forever (bug)")
    parser.add_argument("--work-seconds", type=float, default=0.0, help="extra slow step, for the kill test")
    return parser.parse_args()


class AgentRunner:
    def __init__(self, name, in_topic, group, handler, args):
        self.name, self.in_topic, self.group, self.handler, self.args = name, in_topic, group, handler, args
        self.role = f"{name}-{args.instance}" if args.instance else name
        self.max_attempts = None if args.no_dlq else MAX_ATTEMPTS
        self.store = ProcessedStore()
        self.consumer = self.producer = None

    async def commit(self, msg, why):
        await self.consumer.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
        alog(
            self.role,
            "OFFSET_COMMITTED",
            self.cid_of(msg),
            partition=msg.partition,
            next_offset=msg.offset + 1,
            why=why,
        )

    def cid_of(self, msg):
        record = decode(msg.value)
        return record.get("correlation_id") if record else None

    async def send(self, topic, key, value):
        meta = await self.producer.send_and_wait(topic, encode(value), key=key.encode() if key else None)
        alog(
            self.role,
            "PRODUCED",
            value.get("correlation_id"),
            topic=meta.topic,
            partition=meta.partition,
            offset=meta.offset,
        )

    async def dead_letter(self, msg, record, attempts, error):
        cid = record.get("correlation_id") if record else None
        entry = {
            "correlation_id": cid,
            "failed_agent": self.role,
            "source_topic": msg.topic,
            "source_partition": msg.partition,
            "source_offset": msg.offset,
            "attempts": attempts,
            "error": error,
            "original_value": msg.value.decode("utf-8", errors="replace"),
            "failed_at": now_utc(),
        }
        key = msg.key.decode("utf-8", errors="replace") if msg.key else cid
        await self.send(DEAD_LETTER, key, entry)
        alog(self.role, "MOVED_TO_DEAD_LETTER", cid, topic=DEAD_LETTER, attempts=attempts, error=error)

    async def run_with_retries(self, msg, record):
        attempt = 0
        while True:
            attempt += 1
            try:
                if record is None:
                    raise ValueError("message is not a JSON object")
                return await self.handler(record, msg, self)
            except Exception as exc:  # any failure is retried, then dead-lettered
                error = f"{type(exc).__name__}: {exc}"
                limit = self.max_attempts or "no limit"
                alog(
                    self.role,
                    "PROCESSING_FAILED",
                    record.get("correlation_id") if record else None,
                    offset=msg.offset,
                    attempt=f"{attempt}/{limit}",
                    error=error,
                )
                if self.max_attempts and attempt >= self.max_attempts:
                    await self.dead_letter(msg, record, attempt, error)
                    return None
                await asyncio.sleep(min(2 ** (attempt - 1), 4))  # backoff 1s, 2s, 4s

    async def skip_duplicate(self, msg, cid):
        when = self.store.done_at(self.name, cid)
        if self.args.no_idempotency or not cid or not when:
            return False
        alog(
            self.role,
            "DUPLICATE_SKIPPED",
            cid,
            offset=msg.offset,
            first_processed_at=when,
            note="no LLM call, nothing produced",
        )
        await self.commit(msg, "duplicate skipped")
        return True

    async def handle(self, msg):
        record = decode(msg.value)
        cid = record.get("correlation_id") if record else None
        alog(
            self.role,
            "RECEIVED",
            cid,
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            key=msg.key.decode("utf-8", errors="replace") if msg.key else None,
        )
        if self.args.commit_mode == "before":
            await self.commit(msg, "BEFORE processing (at-most-once)")
        if record and record.get("type") != "ordering_test" and await self.skip_duplicate(msg, cid):
            return
        if cid and (earlier := self.store.mark_started(self.name, cid)):
            alog(
                self.role,
                "REDELIVERED",
                cid,
                offset=msg.offset,
                first_started_at=earlier,
                note="earlier attempt never finished",
            )
        outputs = await self.run_with_retries(msg, record)
        if outputs is None:
            await self.commit(msg, "after dead letter")
            return
        for topic, key, value in outputs:
            await self.send(topic, key, value)
        if cid:
            self.store.mark_done(self.name, cid)
        if self.args.commit_mode == "after":
            await self.commit(msg, "after successful processing")

    async def run(self):
        show_banner(f"{self.role} agent, pid {os.getpid()}, reads {self.in_topic}, group {self.group}")
        mode = {
            "commit_mode": self.args.commit_mode,
            "idempotency": not self.args.no_idempotency,
            "max_attempts": self.max_attempts or "unlimited",
            "work_seconds": self.args.work_seconds,
        }
        alog(self.role, "STARTING", pid=os.getpid(), settings=mode)
        self.producer = await make_producer()
        self.consumer = await make_consumer(self.in_topic, self.group, self.role)
        alog(self.role, "LISTENING", topic=self.in_topic, group=self.group)
        try:
            async for msg in self.consumer:
                await self.handle(msg)
        finally:
            await self.consumer.stop()
            await self.producer.stop()
