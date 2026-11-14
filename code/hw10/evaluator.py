# HW10 Part 2: evaluator joins the plan, draft and final answer by correlation_id and scores them with GEval
# usage (repo root): python -m code.hw10.evaluator             (service: reads s3319_final, writes s3319_evaluations)
#                    python -m code.hw10.evaluator --cid ID    (load one past request from the topics and score it)
#                    python -m code.hw10.evaluator --show ID   (print the saved evaluation of one request)
import argparse
import asyncio
import difflib
import json
import os
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from code.hw10.geval_metrics import METRIC_TIMEOUT, score
from code.hw10.judge import LocalJudge, judge_settings
from code.hw10.traced_qa import EVALUATIONS, ROOT
from code.hw10.tracing import now_iso, write_span
from code.kafka_agents import common as k
from code.kafka_service.settings import PREFIX, banner

from aiokafka import AIOKafkaConsumer, TopicPartition

EVAL_FILE = ROOT / "reports" / "hw10" / "eval" / "eval_results.jsonl"
GROUP = f"{PREFIX}_evaluator_group"
LOOKUP_WAIT = 10.0  # seconds to wait for the plan and draft of a final answer
EVAL_TIMEOUT = 3 * METRIC_TIMEOUT + 10  # hard limit for one whole evaluation
INDEX_LIMIT = 5000  # plans and drafts kept in memory


def plan_text(plan):
    return "\n".join(f"{i}. {step}" for i, step in enumerate(plan or [], 1))


def same_text(a, b):
    return " ".join(str(a).split()).lower() == " ".join(str(b).split()).lower()


def compare(draft_res, final_res, draft, answer):
    changed = not same_text(draft, answer)
    out = {"draft_score": draft_res["score"], "final_score": final_res["score"], "draft_changed": changed}
    out["text_similarity"] = round(difflib.SequenceMatcher(None, str(draft), str(answer)).ratio(), 3)
    if draft_res["score"] is None or final_res["score"] is None:
        return {**out, "difference": None, "interpretation": "Not comparable: a judge score is missing."}
    diff = round(final_res["score"] - draft_res["score"], 2)
    if not changed:
        note = "The Reviewer returned the draft unchanged, so the final answer could not improve on it."
    elif diff > 0:
        note = f"The Reviewer's edit raised helpfulness by {diff:+}."
    elif diff < 0:
        note = f"The Reviewer's edit lowered helpfulness by {diff:+}."
    else:
        note = "The Reviewer changed the wording, but the judge saw no change in helpfulness."
    return {**out, "difference": diff, "interpretation": note}


def source(meta):
    return {"topic": meta[0], "partition": meta[1], "offset": meta[2]} if meta else None


async def evaluate(cid, plan_msg, draft_msg, final_msg, judge=None):
    t0 = time.perf_counter()
    question = final_msg.get("question") or draft_msg.get("question")
    plan, draft, answer = plan_msg.get("plan"), draft_msg.get("draft"), final_msg.get("answer")
    pq = await score("plan_quality", question, plan_text(plan), judge)
    wh = await score("helpfulness", question, draft, judge)
    fh = await score("helpfulness", question, answer, judge)
    named = (("plan_quality", pq), ("writer_helpfulness", wh), ("final_helpfulness", fh))
    errors = [f"{name}: {r['error']}" for name, r in named if r["error"]]
    return {
        "correlation_id": cid,
        "trace_id": cid,
        "status": "error" if errors else "ok",
        "error": "; ".join(errors) or None,
        "evaluated_at": now_iso(),
        "eval_ms": round((time.perf_counter() - t0) * 1000, 1),
        "judge": judge_settings() if judge is None else {"judge_model": judge.model_name, "url": judge.base_url},
        "plan_quality": pq,
        "writer_helpfulness": {**wh, "trace_id": cid},
        "final_helpfulness": {**fh, "final_answer": answer},
        "final_vs_draft": compare(wh, fh, draft, answer),
        "inputs": {
            "question": question,
            "plan": plan,
            "draft": draft,
            "final_answer": answer,
            "review_status": final_msg.get("status"),
            "review_notes": final_msg.get("review_notes"),
        },
        "source": {k_: source(m) for k_, m in (("tasks", plan_msg.get("_meta")), ("drafts", draft_msg.get("_meta")))},
        "trace": final_msg.get("trace"),
    }


def save(result):
    EVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_FILE, "a") as fh:
        fh.write(json.dumps(result, default=str) + "\n")


def show_saved(cid):
    rows = [json.loads(line) for line in EVAL_FILE.read_text().splitlines()] if EVAL_FILE.exists() else []
    found = [r for r in rows if r["trace_id"] == cid]
    if not found:
        print(f"no saved evaluation for {cid} in {EVAL_FILE.relative_to(ROOT)}")
        return
    show(found[-1])
    print(f"\nquestion: {found[-1]['inputs']['question']}")
    print("plan:\n" + plan_text(found[-1]["inputs"]["plan"]))
    print(f"draft: {found[-1]['inputs']['draft']}")
    print(f"final answer: {found[-1]['inputs']['final_answer']}")


def show(result):
    print(f"\ntrace_id: {result['trace_id']}  status: {result['status']}  eval_ms: {result['eval_ms']}")
    if result["error"]:
        print(f"error: {result['error']}")
    for key in ("plan_quality", "writer_helpfulness", "final_helpfulness"):
        r = result[key]
        print(f"{key:<20} score={r['score']}  ({r['ms']} ms)  reason: {r['reason'] or r['error']}")
    c = result["final_vs_draft"]
    print(f"final_vs_draft       draft={c['draft_score']} final={c['final_score']} difference={c['difference']}")
    print(f"                     changed={c['draft_changed']} similarity={c['text_similarity']}  {c['interpretation']}")


def with_meta(msg):
    record = k.decode(msg.value)
    if record is not None:
        record["_meta"] = (msg.topic, msg.partition, msg.offset)  # where the message was read from
    return record


async def load_by_cid(cid):
    found = {}
    for topic in (k.TASKS, k.DRAFTS, k.FINAL):
        for msg in await k.read_all(topic):
            record = with_meta(msg)
            if record and record.get("correlation_id") == cid:
                found[topic] = record  # the latest message wins
    return found.get(k.TASKS), found.get(k.DRAFTS), found.get(k.FINAL)


class EvaluatorService:
    def __init__(self, judge=None):
        self.judge = judge
        self.plans, self.drafts, self.done = {}, {}, set()

    async def start(self):
        self.producer = await k.make_producer()
        self.index = AIOKafkaConsumer(bootstrap_servers=k.KAFKA_BOOTSTRAP, group_id=None, enable_auto_commit=False)
        await self.index.start()
        tps = [TopicPartition(t, p) for t in (k.TASKS, k.DRAFTS) for p in await self.producer.partitions_for(t)]
        self.index.assign(tps)
        await self.index.seek_to_beginning(*tps)  # history too, so a final can always find its plan and draft
        self.finals = AIOKafkaConsumer(
            bootstrap_servers=k.KAFKA_BOOTSTRAP,
            group_id=GROUP,
            auto_offset_reset="latest",  # first start: only new answers, not the HW8 and HW9 history
            enable_auto_commit=False,
            max_poll_interval_ms=900000,  # an evaluation can take minutes
        )
        await self.finals.start()
        self.finals.subscribe([k.FINAL])

    def remember(self, record):
        cid = record.get("correlation_id") if record else None
        if not cid or record.get("type") == "ordering_test":
            return
        store = self.plans if record["_meta"][0] == k.TASKS else self.drafts
        store[cid] = record
        if len(store) > INDEX_LIMIT:
            store.pop(next(iter(store)))  # drop the oldest

    async def index_loop(self):
        while True:
            batch = await self.index.getmany(timeout_ms=500)
            for msg in [m for msgs in batch.values() for m in msgs]:
                self.remember(with_meta(msg))

    async def find_inputs(self, cid):
        deadline = time.monotonic() + LOOKUP_WAIT
        while time.monotonic() < deadline:
            if cid in self.plans and cid in self.drafts:
                return self.plans[cid], self.drafts[cid]
            await asyncio.sleep(0.2)  # the index may be a moment behind
        return self.plans.get(cid), self.drafts.get(cid)

    async def handle(self, msg):
        received_at, final = now_iso(), with_meta(msg)
        cid = final.get("correlation_id") if final else None
        if not cid:
            k.alog("EVALUATOR", "MALFORMED_SKIPPED", offset=msg.offset, value=msg.value[:80].decode("utf-8", "replace"))
            return
        if cid in self.done:
            k.alog("EVALUATOR", "DUPLICATE_SKIPPED", cid, offset=msg.offset)
            return
        reviewed_at = (final.get("trace") or {}).get("reviewed_at")
        if reviewed_at:
            write_span(cid, "final", reviewed_at, received_at, service=f"kafka:{k.FINAL}", consumer="EVALUATOR")
        k.alog("EVALUATOR", "RECEIVED", cid, topic=msg.topic, partition=msg.partition, offset=msg.offset)
        result = await self.run_bounded(cid, final)
        self.done.add(cid)
        attrs = {f: result[f]["score"] for f in ("plan_quality", "writer_helpfulness", "final_helpfulness")}
        write_span(cid, "evaluation", received_at, now_iso(), result["status"], result["error"], "EVALUATOR", **attrs)
        save(result)
        await self.producer.send_and_wait(EVALUATIONS, json.dumps(result, default=str).encode(), key=cid.encode())
        diff = result["final_vs_draft"]["difference"]
        k.alog("EVALUATOR", "EVALUATED", cid, status=result["status"], **attrs, difference=diff)

    async def run_bounded(self, cid, final):
        plan_msg, draft_msg = await self.find_inputs(cid)
        try:
            if not plan_msg or not draft_msg:
                raise LookupError("plan or draft not found for this correlation_id")
            return await asyncio.wait_for(evaluate(cid, plan_msg, draft_msg, final, self.judge), EVAL_TIMEOUT)
        except Exception as exc:  # missing input or a whole evaluation over the limit
            error = f"{type(exc).__name__}: {exc}" if str(exc) else f"{type(exc).__name__}: over {EVAL_TIMEOUT:.0f} s"
            empty = {"score": None, "reason": None, "ms": 0, "status": "error", "error": error}
            return {
                "correlation_id": cid,
                "trace_id": cid,
                "status": "error",
                "error": error,
                "evaluated_at": now_iso(),
                "eval_ms": 0,
                "plan_quality": {**empty, "criterion": "plan_quality"},
                "writer_helpfulness": {**empty, "criterion": "helpfulness", "trace_id": cid},
                "final_helpfulness": {**empty, "criterion": "helpfulness", "final_answer": final.get("answer")},
                "final_vs_draft": {"difference": None, "interpretation": "Not evaluated."},
                "trace": final.get("trace"),
            }

    async def run(self):
        await self.start()
        k.alog("EVALUATOR", "LISTENING", topic=k.FINAL, group=GROUP, writes=EVALUATIONS, judge=judge_settings())
        indexer = asyncio.create_task(self.index_loop())
        try:
            async for msg in self.finals:
                await self.handle(msg)
                await self.finals.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
        finally:
            indexer.cancel()
            await self.finals.stop()
            await self.index.stop()
            await self.producer.stop()


async def evaluate_one(cid, judge):
    plan_msg, draft_msg, final_msg = await load_by_cid(cid)
    missing = [n for n, m in (("plan", plan_msg), ("draft", draft_msg), ("final", final_msg)) if not m]
    if missing:
        print(f"cannot evaluate {cid}: no {', '.join(missing)} message in the topics")
        return None
    result = await asyncio.wait_for(evaluate(cid, plan_msg, draft_msg, final_msg, judge), EVAL_TIMEOUT)
    show(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cid", help="score one past request, loaded from the topics")
    parser.add_argument("--show", help="print the saved evaluation of one request")
    parser.add_argument("--judge-url", help="another Ollama URL, for the judge-unavailable test")
    parser.add_argument("--judge-timeout", type=float, help="seconds per judge call, for the hang test")
    args = parser.parse_args()
    one = args.show or args.cid
    banner("HW10 Part 2 evaluator" + (f" for {one}" if one else ""))
    if args.show:
        show_saved(args.show)
        raise SystemExit(0)
    judge = None
    if args.judge_url or args.judge_timeout:
        judge = LocalJudge(**{k_: v for k_, v in (("base_url", args.judge_url), ("timeout", args.judge_timeout)) if v})
    asyncio.run(evaluate_one(args.cid, judge) if args.cid else EvaluatorService(judge).run())
