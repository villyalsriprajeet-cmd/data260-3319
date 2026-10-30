# HW8 Part 3.I: re-send a delivered message, same key/value/correlation_id
# usage: python replay_message.py --cid ID [--topic s3319_tasks]
import argparse
import asyncio

from common import TASKS, alog, decode, make_producer, read_all, show_banner


async def main(args):
    show_banner(f"Part 3 duplicate replay of {args.cid} on {args.topic}")
    msgs = [m for m in await read_all(args.topic) if (decode(m.value) or {}).get("correlation_id") == args.cid]
    if not msgs:
        print(f"no message with correlation_id={args.cid} in {args.topic}")
        return
    original = msgs[0]
    alog("REPLAY", "ORIGINAL_FOUND", args.cid, topic=args.topic, partition=original.partition, offset=original.offset)
    producer = await make_producer()
    meta = await producer.send_and_wait(args.topic, original.value, key=original.key)  # byte-for-byte copy
    await producer.stop()
    alog(
        "REPLAY",
        "DUPLICATE_SENT",
        args.cid,
        topic=meta.topic,
        partition=meta.partition,
        offset=meta.offset,
        note="same key, same value, same correlation_id",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cid", required=True)
    parser.add_argument("--topic", default=TASKS)
    asyncio.run(main(parser.parse_args()))
