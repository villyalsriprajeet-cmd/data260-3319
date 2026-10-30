# HW8 Part 2 Writer: plan from s3319_tasks, draft to s3319_drafts
# Part 3 adds flags that switch each fix off for the before runs
import asyncio
import csv

from common import DRAFTS, PREFIX, RAW_DIR, TASKS, alog, ask_llm, first_text, now_utc
from runtime import AgentRunner, agent_args

GROUP = f"{PREFIX}_writer_group"
SYSTEM = (
    "You are the Writer agent of a community sports league fixtures assistant. "
    "Follow the plan step by step and write a helpful answer to the question in at most "
    "120 words. Use only facts given in the question; do not invent dates, scores or names. "
    'Reply with ONE JSON object only: {"draft": "your answer"}'
)
ORDER_FIELDS = ["run", "msg_no", "entity", "seq", "partition", "offset", "writer", "processed_at"]


async def record_ordering(record, msg, runner):
    await asyncio.sleep(record.get("work_ms", 0) / 1000)  # seeded work time per message
    row = {
        "run": record["run"],
        "msg_no": record["msg_no"],
        "entity": record["entity"],
        "seq": record["seq"],
        "partition": msg.partition,
        "offset": msg.offset,
        "writer": runner.role,
        "processed_at": now_utc(),
    }
    path = RAW_DIR / f"ordering_{record['run']}_{runner.role}.csv"
    new = not path.exists()
    with open(path, "a", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=ORDER_FIELDS)
        if new:
            out.writeheader()
        out.writerow(row)
    alog(
        runner.role,
        "ORDERING_PROCESSED",
        record["correlation_id"],
        entity=record["entity"],
        seq=record["seq"],
        partition=msg.partition,
        offset=msg.offset,
    )
    return []  # test message: recorded only, not forwarded


async def write_draft(record, msg, runner):
    if record.get("type") == "ordering_test":
        return await record_ordering(record, msg, runner)
    question, plan, cid = record.get("question"), record.get("plan"), record.get("correlation_id")
    if not cid or not isinstance(question, str) or not isinstance(plan, list) or not plan:
        raise ValueError("task needs correlation_id, question and a non-empty plan")
    if runner.args.work_seconds:
        alog(runner.role, "WORKING_SLOW_STEP", cid, seconds=runner.args.work_seconds, note="kill -9 now to test")
        await asyncio.sleep(runner.args.work_seconds)
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))
    reply, usage = await ask_llm(SYSTEM, f"Question: {question}\n\nPlan:\n{steps}")
    draft = first_text(reply, "draft", "answer")
    if not draft:
        raise ValueError("LLM returned no draft")
    alog(runner.role, "DRAFTED", cid, words=len(draft.split()), tokens=usage["total_tokens"])
    trace = {**record.get("trace", {}), "drafted_at": now_utc()}
    out = {"correlation_id": cid, "question": question, "plan": plan, "draft": draft, "trace": trace}
    return [(DRAFTS, cid, out)]


if __name__ == "__main__":
    asyncio.run(AgentRunner("WRITER", TASKS, GROUP, write_draft, agent_args("Writer")).run())
