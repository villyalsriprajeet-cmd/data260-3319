# HW8 Part 2: send a question to s3319_inbox, wait for s3319_final
# usage: python send_question.py [--question "..."] [--no-wait] [--timeout 600]
import argparse
import asyncio
import json
import uuid

from common import (
    FINAL,
    INBOX,
    RAW_DIR,
    alog,
    decode,
    encode,
    journey_lines,
    make_producer,
    now_utc,
    show_banner,
    tail_consumer,
)

QUESTION = (
    "Our team, the Spartans, plays the Eagles at Riverside Park this Sunday at 2 PM. "
    "League reminders go out 24 hours before kickoff. As team manager, what should I do "
    "between now and kickoff to get this fixture ready?"
)


async def wait_for_final(consumer, cid, timeout):
    async def find():
        async for msg in consumer:
            record = decode(msg.value)
            if record and record.get("correlation_id") == cid:
                alog("CLIENT", "FINAL_RECEIVED", cid, topic=msg.topic, partition=msg.partition, offset=msg.offset)
                return record

    return await asyncio.wait_for(find(), timeout=timeout)


async def main(args):
    show_banner("Part 2 send_question.py")
    cid = str(uuid.uuid4())
    message = {"correlation_id": cid, "question": args.question, "trace": {"asked_at": now_utc()}}
    consumer = None if args.no_wait else await tail_consumer(FINAL)  # listen before sending
    producer = await make_producer()
    meta = await producer.send_and_wait(INBOX, encode(message), key=cid.encode())
    await producer.stop()
    alog(
        "CLIENT", "QUESTION_SENT", cid, topic=meta.topic, partition=meta.partition, offset=meta.offset, message=message
    )
    if consumer is None:
        return
    try:
        final = await wait_for_final(consumer, cid, args.timeout)
    finally:
        await consumer.stop()
    print(f"\nFinal JSON from {FINAL}:\n{json.dumps(final, indent=2)}")
    print(f"\ncorrelation_id preserved end to end: {final.get('correlation_id') == cid}")
    print("\nMessage journey (all agents, same correlation_id):")
    print("\n".join(journey_lines(cid)))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "p2_final_message.json").write_text(json.dumps(final, indent=2) + "\n")
    show_banner("end of send_question.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=600)
    asyncio.run(main(parser.parse_args()))
