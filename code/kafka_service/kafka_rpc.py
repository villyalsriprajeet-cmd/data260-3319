# HW8 Part 1 Kafka client used by FastAPI
import asyncio
import json

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from settings import KAFKA_BOOTSTRAP, REQUEST_TOPIC, RESPONSE_TOPIC, RPC_TIMEOUT_SECONDS, log


class KafkaRPC:
    def __init__(self):
        self.producer = None
        self.consumer = None
        self.pending = {}  # requests waiting for a reply
        self.task = None

    async def start(self):
        for attempt in range(1, 31):
            try:
                await self.open_clients()
                break
            except Exception as exc:  # Kafka may still be starting
                log("API", "WAITING_FOR_KAFKA", attempt=attempt, error=type(exc).__name__)
                await asyncio.sleep(2)
        else:
            raise RuntimeError("Kafka not reachable")
        self.task = asyncio.create_task(self.consume_responses())
        log("API", "KAFKA_RPC_READY", request_topic=REQUEST_TOPIC, response_topic=RESPONSE_TOPIC)

    async def open_clients(self):
        self.producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all")
        await self.producer.start()
        partitions = await self.producer.partitions_for(RESPONSE_TOPIC)
        self.consumer = AIOKafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, group_id=None, enable_auto_commit=False)
        await self.consumer.start()
        tps = [TopicPartition(RESPONSE_TOPIC, p) for p in sorted(partitions)]
        self.consumer.assign(tps)  # read the replies topic directly
        await self.consumer.seek_to_end(*tps)  # skip old replies
        for tp in tps:
            await self.consumer.position(tp)

    async def stop(self):
        if self.task:
            self.task.cancel()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def consume_responses(self):
        async for msg in self.consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            if not isinstance(data, dict):
                log("API", "BAD_RESPONSE_SKIPPED", offset=msg.offset)
                continue
            cid = data.get("correlation_id")
            future = self.pending.pop(cid, None)
            log("API", "RECEIVED_RESPONSE", cid, topic=msg.topic, partition=msg.partition, offset=msg.offset)
            if future and not future.done():
                future.set_result(data)
                log("API", "MATCHED_PENDING_REQUEST", cid, pending_left=len(self.pending))
            elif not future:
                log("API", "NO_PENDING_REQUEST", cid, note="reply for another caller or a timed-out request")

    async def request(self, cid, operation, data):
        message = {"correlation_id": cid, "reply_to": RESPONSE_TOPIC, "operation": operation, "data": data}
        future = asyncio.get_running_loop().create_future()
        self.pending[cid] = future
        meta = await self.producer.send_and_wait(REQUEST_TOPIC, json.dumps(message).encode(), key=cid.encode())
        log("API", "SENT_REQUEST", cid, topic=meta.topic, partition=meta.partition, offset=meta.offset, message=message)
        try:
            return await asyncio.wait_for(future, timeout=RPC_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.pending.pop(cid, None)
            log("API", "TIMEOUT", cid, seconds=RPC_TIMEOUT_SECONDS)
            return {"correlation_id": cid, "operation": operation, "success": False, "error": "Timed out waiting"}
