# HW8 Part 1 worker: reads fixture requests and sends replies
import asyncio
import json

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from fixture_store import process_request, reply_topic
from settings import KAFKA_BOOTSTRAP, REQUEST_TOPIC, WORKER_GROUP, banner, log

FIXTURES = {}  # plain dict store
RESPONSES_BY_CID = {}  # replies already sent, to skip duplicates


def decode(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None  # bad JSON gets a clean error later


async def connect():
    consumer = AIOKafkaConsumer(
        REQUEST_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=WORKER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,  # commit only after the reply is sent
    )
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all")
    for attempt in range(1, 31):
        try:
            await producer.start()
            await consumer.start()
            return consumer, producer
        except Exception as exc:  # Kafka may still be starting
            log("WORKER", "WAITING_FOR_KAFKA", attempt=attempt, error=type(exc).__name__)
            await asyncio.sleep(2)
    raise RuntimeError("Kafka not reachable")


def build_response(request):
    cid = request.get("correlation_id") if isinstance(request, dict) else None
    if cid and cid in RESPONSES_BY_CID:
        log("WORKER", "DUPLICATE_SKIPPED", cid, note="same correlation_id seen before, resending stored reply")
        return {**RESPONSES_BY_CID[cid], "duplicate": True}
    response = process_request(request, FIXTURES)
    if cid:
        RESPONSES_BY_CID[cid] = response
    return response


async def handle(msg, producer, consumer):
    request = decode(msg.value)
    cid = request.get("correlation_id") if isinstance(request, dict) else None
    log("WORKER", "RECEIVED", cid, topic=msg.topic, partition=msg.partition, offset=msg.offset, message=request)
    response = build_response(request)
    log("WORKER", "PROCESSED", cid, operation=response.get("operation"), success=response["success"])
    target = reply_topic(request)
    meta = await producer.send_and_wait(target, json.dumps(response).encode(), key=(cid or "").encode() or None)
    log(
        "WORKER", "SENT_RESPONSE", cid, topic=meta.topic, partition=meta.partition, offset=meta.offset, message=response
    )
    await consumer.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
    log("WORKER", "OFFSET_COMMITTED", cid, partition=msg.partition, next_offset=msg.offset + 1)


async def main():
    banner("Part 1 worker (consumer)")
    consumer, producer = await connect()
    print("Consumer is ready and listening...", flush=True)
    log("WORKER", "LISTENING", topic=REQUEST_TOPIC, group=WORKER_GROUP, bootstrap=KAFKA_BOOTSTRAP)
    try:
        async for msg in consumer:
            await handle(msg, producer, consumer)
    finally:
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
