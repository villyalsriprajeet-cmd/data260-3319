# HW8 Part 3.III: a poison message, then a good task on the same partition
# usage: python send_poison.py
import asyncio
import json
import uuid

from common import RAW_DIR, TASKS, alog, encode, make_producer, now_utc, show_banner

KEY = b"poison-demo"  # same key, same partition: the good task waits behind it
POISON = b'{"correlation_id": "poison-0001", "plan": [ <<< not valid JSON'
FOLLOW_UP_QUESTION = (
    "The Spartans' next fixture is Sunday at 2 PM at Riverside Park. What should the captain remind the team?"
)


async def main():
    show_banner("Part 3 send_poison.py")
    good_cid = str(uuid.uuid4())
    good = {
        "correlation_id": good_cid,
        "type": "answer_task",
        "question": FOLLOW_UP_QUESTION,
        "plan": ["State the fixture time and venue.", "List what players should bring.", "Add a reminder."],
        "trace": {"asked_at": now_utc(), "planned_at": now_utc()},
    }
    producer = await make_producer()
    bad = await producer.send_and_wait(TASKS, POISON, key=KEY)
    alog("POISON", "POISON_SENT", "poison-0001", topic=TASKS, partition=bad.partition, offset=bad.offset)
    ok = await producer.send_and_wait(TASKS, encode(good), key=KEY)
    alog("POISON", "GOOD_TASK_SENT_BEHIND_IT", good_cid, topic=TASKS, partition=ok.partition, offset=ok.offset)
    await producer.stop()
    info = {
        "poison": {"partition": bad.partition, "offset": bad.offset, "value": POISON.decode()},
        "follow_up": {"correlation_id": good_cid, "partition": ok.partition, "offset": ok.offset},
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "p3_poison_sent.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
