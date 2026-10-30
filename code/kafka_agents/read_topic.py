# HW8: list and count the messages in a topic, optionally for one cid
# usage: python read_topic.py TOPIC [--cid ID] [--last N] [--save x.json]
import argparse
import asyncio
import json

from common import RAW_DIR, decode, read_all, show_banner


def row(msg):
    record = decode(msg.value)
    value = record if record is not None else msg.value.decode("utf-8", errors="replace")
    key = msg.key.decode("utf-8", errors="replace") if msg.key else None
    return {"partition": msg.partition, "offset": msg.offset, "key": key, "value": value}


async def main(args):
    show_banner(f"read_topic {args.topic}" + (f" cid={args.cid}" if args.cid else ""))
    rows = [row(m) for m in await read_all(args.topic)]
    if args.cid:
        rows = [r for r in rows if isinstance(r["value"], dict) and r["value"].get("correlation_id") == args.cid]
    for r in rows[-args.last :] if args.last else rows:
        print(json.dumps(r))
    print(f"\n{len(rows)} message(s) in {args.topic}" + (f" with correlation_id={args.cid}" if args.cid else ""))
    if args.save:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / args.save).write_text(json.dumps(rows, indent=2) + "\n")
        print(f"saved reports/hw08/raw/{args.save}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("topic")
    parser.add_argument("--cid")
    parser.add_argument("--last", type=int, default=0)
    parser.add_argument("--save")
    asyncio.run(main(parser.parse_args()))
