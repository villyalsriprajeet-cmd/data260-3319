# HW8 Parts 2 and 3 consume loop: skip duplicates, retry, dead letter, commit
# HW10 Part 4.1 adds a queue-wait span and a processing span per message, and a fault hook
import argparse
import asyncio
import os
from code.hw10.tracing import now_iso, write_span

from aiokafka import TopicPartition
from aiokafka.errors import CommitFailedError
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

QUEUE_FROM = {"PLANNER": ("inbox", "asked_at"), "WRITER": ("tasks", "planned_at"), "REVIEWER": ("drafts", "drafted_at")}


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
        self.last_error, self.last_attempts = None, 0

    async def commit(self, msg, why):
        try:
            await self.consumer.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
        except CommitFailedError:  # HW10: group rebalanced in a broker stall; a redelivery is skipped as duplicate
            alog(self.role, "COMMIT_FAILED_REBALANCED", self.cid_of(msg), partition=msg.partition, offset=msg.offset)
            return
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
            self.last_attempts = attempt
            try:
                if record is None:
                    raise ValueError("message is not a JSON object")
                if (record.get("trace") or {}).get("inject_fault") == self.name:  # HW10 failed-trace test
                    raise RuntimeError(f"injected fault at {self.name} for the HW10 failed-trace test")
                return await self.handler(record, msg, self)
            except Exception as exc:  # any failure is retried, then dead-lettered
                error = f"{type(exc).__name__}: {exc}"
                self.last_error = error
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

    def queue_span(self, record, cid, received_at):
        stage, key = QUEUE_FROM.get(self.name, (None, None))
        sent_at = (record.get("trace") or {}).get(key)
        if stage and sent_at:
            write_span(cid, stage, sent_at, received_at, service=f"kafka:{self.in_topic}", consumer=self.role)

    def work_span(self, cid, received_at, done_at, outputs):
        failed = outputs is None
        status, error = ("error", self.last_error) if failed else ("ok", None)
        attrs = {"attempts": self.last_attempts, "dead_lettered": failed}
        write_span(cid, self.name.lower(), received_at, done_at, status, error, service=self.role, **attrs)

    async def handle(self, msg):
        received_at = now_iso()
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
        traced = bool(cid) and record.get("type") != "ordering_test"
        if traced:
            self.queue_span(record, cid, received_at)
        outputs = await self.run_with_retries(msg, record)
        done_at = now_iso()  # work ends here; the send below counts as queue wait
        if outputs is None:
            if traced:
                self.work_span(cid, received_at, done_at, None)
            await self.commit(msg, "after dead letter")
            return
        for topic, key, value in outputs:
            await self.send(topic, key, value)
        if traced:
            self.work_span(cid, received_at, done_at, outputs)
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
