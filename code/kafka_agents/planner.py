# HW8 Part 2 Planner: question from s3319_inbox, plan to s3319_tasks
import asyncio

from common import INBOX, PREFIX, TASKS, alog, ask_llm, now_utc
from runtime import AgentRunner, agent_args

GROUP = f"{PREFIX}_planner_group"
SYSTEM = (
    "You are the Planner agent of a community sports league fixtures assistant. "
    "Break the user's question into exactly 3 short, concrete steps that a Writer agent "
    "should follow to answer it. Use only facts given in the question. "
    'Reply with ONE JSON object only: {"plan": ["step 1", "step 2", "step 3"]}'
)
FALLBACK_PLAN = [
    "Restate the fixture details given in the question.",
    "List the concrete actions the user should take before kickoff.",
    "Finish with one short reminder about timing.",
]


def clean_plan(reply):
    plan = reply.get("plan")
    if not isinstance(plan, list):
        return None
    steps = [str(s).strip() for s in plan if str(s).strip()]
    return steps[:5] if steps else None


async def plan_question(record, msg, runner):
    question = record.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is missing or empty")
    reply, usage = await ask_llm(SYSTEM, f"Question: {question}")
    plan = clean_plan(reply)
    if plan is None:
        alog(runner.role, "LLM_PLAN_UNUSABLE_USING_FALLBACK", record["correlation_id"])
        plan = FALLBACK_PLAN
    cid = record["correlation_id"]
    alog(runner.role, "PLANNED", cid, steps=len(plan), tokens=usage["total_tokens"], plan=plan)
    trace = {**record.get("trace", {}), "planned_at": now_utc()}
    task = {"correlation_id": cid, "type": "answer_task", "question": question, "plan": plan, "trace": trace}
    return [(TASKS, cid, task)]  # keyed by correlation_id


if __name__ == "__main__":
    asyncio.run(AgentRunner("PLANNER", INBOX, GROUP, plan_question, agent_args("Planner")).run())
