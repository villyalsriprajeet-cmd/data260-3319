# HW8 Part 2 Reviewer: draft from s3319_drafts, answer to s3319_final
import asyncio

from common import DRAFTS, FINAL, PREFIX, alog, ask_llm, now_utc
from runtime import AgentRunner, agent_args

GROUP = f"{PREFIX}_reviewer_group"
MAX_WORDS = 150
SYSTEM = (
    "You are the Reviewer agent of a community sports league fixtures assistant. "
    "Check that the draft answers the question, follows the plan, is at most 150 words and "
    "invents no facts that are not in the question. Fix small problems yourself. "
    'Reply with ONE JSON object only: {"status": "approved" or "needs_revision", '
    '"answer": "the final answer text", "notes": "one sentence"}'
)


def decide(reply, draft):
    given = reply.get("answer")
    answer = given.strip() if isinstance(given, str) and given.strip() else draft.strip()  # fall back to draft
    status = "approved" if str(reply.get("status", "")).lower() == "approved" else "needs_revision"
    checks = {"answer_not_empty": bool(answer), "within_word_limit": len(answer.split()) <= MAX_WORDS}
    if not all(checks.values()):
        status = "needs_revision"  # code checks can veto the model's approval
    return status, answer, checks


async def review_draft(record, msg, runner):
    cid, draft, question = record.get("correlation_id"), record.get("draft"), record.get("question")
    if not cid or not isinstance(draft, str) or not draft.strip():
        raise ValueError("draft message needs correlation_id and a draft")
    user = f"Question: {question}\n\nPlan: {record.get('plan')}\n\nDraft: {draft}"
    reply, usage = await ask_llm(SYSTEM, user)
    status, answer, checks = decide(reply, draft)
    alog(runner.role, "REVIEWED", cid, status=status, tokens=usage["total_tokens"], checks=checks)
    trace = {**record.get("trace", {}), "reviewed_at": now_utc()}
    final = {
        "correlation_id": cid,
        "status": status,
        "answer": answer,
        "question": question,
        "review_notes": str(reply.get("notes", "")).strip(),
        "checks": checks,
        "trace": trace,
    }
    return [(FINAL, cid, final)]


if __name__ == "__main__":
    asyncio.run(AgentRunner("REVIEWER", DRAFTS, GROUP, review_draft, agent_args("Reviewer")).run())
