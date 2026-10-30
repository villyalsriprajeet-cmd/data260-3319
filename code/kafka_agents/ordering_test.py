# HW8 Part 3.IV: 20 related messages, 2 partitions, 2 Writers, VERIFY_SEED
# usage: python ordering_test.py nokey   then   python ordering_test.py keyed
import argparse
import asyncio
import csv
import json
import random
import time
import uuid

from common import ORDER_SEED, RAW_DIR, TASKS, alog, encode, make_producer, now_utc, show_banner

EVENTS = ["FIXTURE_CREATED", "VENUE_CONFIRMED", "KICKOFF_SET", "TICKETS_RELEASED", "FIXTURE_CONFIRMED"]
N_FIXTURES = 4  # 4 fixtures x 5 updates = 20 related messages


def build_messages(run):
    rng = random.Random(ORDER_SEED)
    codes = sorted({f"FX-{rng.randint(10000, 99999)}" for _ in range(20)})[:N_FIXTURES]
    queues = {code: list(range(1, len(EVENTS) + 1)) for code in codes}
    messages = []
    while any(queues.values()):
        code = rng.choice([c for c in codes if queues[c]])  # interleave, keep each fixture's own order
        seq = queues[code].pop(0)
        msg_no = len(messages) + 1
        cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"s3319-{run}-{ORDER_SEED}-{msg_no}"))
        messages.append(
            {
                "correlation_id": cid,
                "type": "ordering_test",
                "run": run,
                "msg_no": msg_no,
                "entity": code,
                "seq": seq,
                "event": EVENTS[seq - 1],
                "work_ms": rng.randint(50, 600),
            }
        )
    return messages


async def send_all(run, keyed):
    random.seed(ORDER_SEED)  # the no-key partitioner picks randomly; seeding makes it repeatable
    producer = await make_producer()
    sent = []
    for msg in build_messages(run):
        key = msg["entity"].encode() if keyed else None  # keyed run: key = related fixture
        meta = await producer.send_and_wait(TASKS, encode(msg), key=key)
        sent.append(
            {
                **msg,
                "key": msg["entity"] if keyed else None,
                "partition": meta.partition,
                "offset": meta.offset,
                "sent_at": now_utc(),
            }
        )
        alog(
            "ORDER-TEST",
            "SENT",
            msg["correlation_id"],
            run=run,
            msg_no=msg["msg_no"],
            entity=msg["entity"],
            seq=msg["seq"],
            key=sent[-1]["key"],
            partition=meta.partition,
        )
    await producer.stop()
    return sent


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)


def load_processed(run):
    rows = []
    for path in RAW_DIR.glob(f"ordering_{run}_WRITER*.csv"):
        with open(path) as fh:
            rows += list(csv.DictReader(fh))
    return sorted(rows, key=lambda r: (r["processed_at"], r["writer"], int(r["offset"])))  # ties: offset order


def summarize(run, rows):
    entities = {}
    for r in rows:
        e = entities.setdefault(r["entity"], {"partitions": set(), "writers": set(), "order": []})
        e["partitions"].add(int(r["partition"]))
        e["writers"].add(r["writer"])
        e["order"].append(int(r["seq"]))
    table = {
        code: {
            "partitions": sorted(e["partitions"]),
            "writers": sorted(e["writers"]),
            "processed_seq_order": e["order"],
            "in_order": e["order"] == sorted(e["order"]),
        }
        for code, e in sorted(entities.items())
    }
    return {
        "run": run,
        "verify_seed": ORDER_SEED,
        "messages_processed": len(rows),
        "entities_in_one_partition": sum(len(t["partitions"]) == 1 for t in table.values()),
        "entities_in_order": sum(t["in_order"] for t in table.values()),
        "entities": table,
    }


def print_summary(summary):
    print(f"\nOrdering run '{summary['run']}' (VERIFY_SEED {ORDER_SEED})")
    print(f"{'fixture':<10} {'partitions':<11} {'writers':<20} {'processed seq order':<20} in order?")
    for code, t in summary["entities"].items():
        print(
            f"{code:<10} {str(t['partitions']):<11} {', '.join(t['writers']):<20} "
            f"{str(t['processed_seq_order']):<20} {'YES' if t['in_order'] else 'NO'}"
        )
    n = len(summary["entities"])
    print(f"\nmessages processed: {summary['messages_processed']}/20")
    print(f"fixtures kept in one partition: {summary['entities_in_one_partition']}/{n}")
    print(f"fixtures processed in order: {summary['entities_in_order']}/{n}")


async def main(args):
    show_banner(f"Part 3 ordering test, run={args.run}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for old in RAW_DIR.glob(f"ordering_{args.run}_*"):
        old.unlink()  # fresh files for this run
    sent = await send_all(args.run, keyed=args.run == "keyed")
    write_csv(RAW_DIR / f"ordering_{args.run}_sent.csv", sent)
    deadline = time.time() + args.wait
    while len(load_processed(args.run)) < len(sent) and time.time() < deadline:
        await asyncio.sleep(1)  # wait for both Writers to finish
    rows = load_processed(args.run)
    if rows:
        write_csv(RAW_DIR / f"ordering_{args.run}_processed.csv", rows)
    summary = summarize(args.run, rows)
    (RAW_DIR / f"ordering_{args.run}_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("\nprocessing order (both Writers, by time):")
    for r in rows:
        print(
            f"  {r['processed_at']}  {r['writer']:<9} p{r['partition']} off={r['offset']:<4} "
            f"#{r['msg_no']:>2} {r['entity']} seq {r['seq']}"
        )
    print_summary(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", choices=["nokey", "keyed"])
    parser.add_argument("--wait", type=float, default=90)
    asyncio.run(main(parser.parse_args()))
