# HW10 Part 3.1: freeze 20 real Writer drafts in eval_cases.json, then label them by hand in human_labels.csv
# usage (repo root): python -m code.hw10.p3_cases collect   (stop the evaluator first: the judge must not see them)
#                    python -m code.hw10.p3_cases label     (you type a 1 to 5 helpfulness score per draft)
#                    python -m code.hw10.p3_cases show      (cases, labels and the score spread)
import argparse
import asyncio
import csv
import hashlib
import json
import sys
import time
import uuid
from code.hw9.qa_service import FACTS_SQL, facts_text, fixture_codes
from code.hw10.geval_metrics import HELPFULNESS_LEVELS, HELPFULNESS_STEPS
from code.hw10.traced_qa import ROOT, tail_many
from code.hw10.tracing import now_iso
from code.kafka_agents import common as k
from code.kafka_service.settings import banner
from collections import Counter

EVAL_DIR = ROOT / "reports" / "hw10" / "eval"
CASES_FILE = EVAL_DIR / "eval_cases.json"
PARTIAL_FILE = EVAL_DIR / "eval_cases.partial.json"  # progress, so a broker hiccup does not lose finished drafts
LABELS_FILE = EVAL_DIR / "human_labels.csv"
LABEL_FIELDS = ["case_id", "trace_id", "human_score", "note", "labeled_at"]
WAIT_S = 300  # seconds to wait for one draft and final answer
QUESTIONS = [
    "How many tickets are left for fixture FX-01207?",
    "Where is fixture FX-02450 being played, and which team is at home?",
    "Is fixture FX-03333 close to selling out? Give the ticket count.",
    "Which teams are playing in fixture FX-04012?",
    "Can a family of five still get seats for fixture FX-00777?",
    "What is the venue for fixture FX-09999?",
    "How many tickets remain for FX-07500 and FX-00118 combined?",
    "What was the final score of fixture FX-04999?",
    "Who is refereeing fixture FX-01860?",
    "What time does fixture FX-02905 kick off?",
    "Compare ticket availability for FX-00450 and FX-03120. Which one has more seats left?",
    "What should a volunteer bring when helping at a Saturday league fixture?",
    "How can a team request to reschedule a league fixture?",
    "What should players do to warm up safely before a youth football fixture?",
    "How should spectators behave at a community league match?",
    "What happens if a team does not show up for a scheduled fixture?",
    "Give me tips for parking near a busy community sports venue on match day.",
    "What is the capital of France?",
    "Tell me everything about the league.",
    "Should I buy tickets for fixture FX-01544 now or wait until match day?",
]


def load_facts(question):
    from code.api.database import engine  # MySQL s3319_rel, as in HW9

    codes = fixture_codes(question)
    if not codes:
        return ""
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(FACTS_SQL, {"codes": codes})]
    return facts_text(codes, rows)


async def run_one(producer, consumer, question):
    cid = str(uuid.uuid4())
    full = question + load_facts(question)
    trace = {"trace_id": cid, "source": "hw10_p3_cases", "asked_at": now_iso()}
    message = {"correlation_id": cid, "question": full, "trace": trace}
    await producer.send_and_wait(k.INBOX, k.encode(message), key=cid.encode())
    got, deadline = {}, time.monotonic() + WAIT_S
    while time.monotonic() < deadline and not (got.get("draft") and got.get("final")):
        batch = await consumer.getmany(timeout_ms=500)
        for msg in [m for msgs in batch.values() for m in msgs]:
            record = k.decode(msg.value)
            if not record or record.get("correlation_id") != cid:
                continue
            if msg.topic == k.DEAD_LETTER:
                return cid, None, f"dead letter: {record.get('error')}"
            name = "draft" if msg.topic == k.DRAFTS else "final"
            got[name] = (record, {"topic": msg.topic, "partition": msg.partition, "offset": msg.offset})
    if not (got.get("draft") and got.get("final")):
        return cid, None, f"timeout after {WAIT_S} s"
    (draft, src), (final, _) = got["draft"], got["final"]
    case = {
        "trace_id": cid,
        "user_question": question,
        "question": full,
        "plan": draft.get("plan"),
        "draft": draft.get("draft"),
        "final_answer": final.get("answer"),
        "review_status": final.get("status"),
        "writer_model": "qwen2.5:3b (HW8 Writer)",
        "collected_at": now_iso(),
        "source": src,
    }
    return cid, case, None


async def collect(force):
    if CASES_FILE.exists() and not force:
        sys.exit(f"{CASES_FILE.relative_to(ROOT)} already exists and is frozen; use --force only to rebuild it")
    cases = json.loads(PARTIAL_FILE.read_text()) if PARTIAL_FILE.exists() and not force else []
    if cases:
        print(f"resuming: {len(cases)} drafts already collected in {PARTIAL_FILE.relative_to(ROOT)}", flush=True)
    done = {c["case_id"] for c in cases}
    producer = await k.make_producer()
    consumer = await tail_many(k, [k.DRAFTS, k.FINAL, k.DEAD_LETTER])  # listen before sending
    try:
        for i, question in enumerate(QUESTIONS, 1):
            if f"C{i:02d}" in done:
                continue
            t0 = time.perf_counter()
            for attempt in (1, 2):
                cid, case, error = await run_one(producer, consumer, question)
                if case:
                    break
                print(f"  C{i:02d} attempt {attempt} failed: {error}", flush=True)
            if not case:
                sys.exit(f"stopped: C{i:02d} gave no draft twice; finished drafts are kept, run collect again")
            cases.append({"case_id": f"C{i:02d}", **case})
            EVAL_DIR.mkdir(parents=True, exist_ok=True)
            PARTIAL_FILE.write_text(json.dumps(cases, indent=2) + "\n")  # saved after every draft
            print(f"C{i:02d} {time.perf_counter() - t0:5.1f} s  {question}\n     draft: {case['draft']}", flush=True)
    finally:
        await consumer.stop()
        await producer.stop()
    body = json.dumps(cases, sort_keys=True).encode()
    frozen = {"frozen_at": now_iso(), "count": len(cases), "sha256": hashlib.sha256(body).hexdigest(), "cases": cases}
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    CASES_FILE.write_text(json.dumps(frozen, indent=2) + "\n")
    PARTIAL_FILE.unlink(missing_ok=True)
    print(f"\nfroze {len(cases)} drafts in {CASES_FILE.relative_to(ROOT)}  sha256={frozen['sha256'][:16]}")


def load_cases():
    return json.loads(CASES_FILE.read_text())["cases"]


def load_labels():
    if not LABELS_FILE.exists():
        return {}
    with open(LABELS_FILE, newline="") as fh:
        return {row["case_id"]: row for row in csv.DictReader(fh)}


def print_rubric():
    print("Helpfulness rubric (the same steps and levels the judge uses):")
    for step in HELPFULNESS_STEPS:
        print(f"  * {step}")
    for score, text in enumerate(HELPFULNESS_LEVELS, 1):
        print(f"  {score} = {text}")


def ask(prompt, default="q"):
    try:
        return input(prompt).strip()
    except EOFError:  # Ctrl+D stops cleanly
        return default


def ask_score(case_id):
    while True:
        raw = ask(f"Your helpfulness score for {case_id} (1 to 5, or q to stop): ").lower()
        if raw == "q" or raw in {"1", "2", "3", "4", "5"}:
            return raw
        print("  please type a whole number from 1 to 5, or q")


def label():
    cases, labels = load_cases(), load_labels()
    todo = [c for c in cases if c["case_id"] not in labels]
    print_rubric()
    print(f"\n{len(labels)} of {len(cases)} already labeled, {len(todo)} to go. No judge score is shown here.\n")
    new_file = not LABELS_FILE.exists()
    with open(LABELS_FILE, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LABEL_FIELDS)
        if new_file:
            writer.writeheader()
        for case in todo:
            print(f"\n{case['case_id']}  question: {case['question']}\n\n  WRITER DRAFT: {case['draft']}\n")
            raw = ask_score(case["case_id"])
            if raw == "q":
                print("stopped; run the same command again to continue")
                return
            note = ask("  short reason (optional, Enter to skip): ", default="")
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "trace_id": case["trace_id"],
                    "human_score": int(raw),
                    "note": note,
                    "labeled_at": now_iso(),
                }
            )
            fh.flush()  # saved right away
    print(f"\nall {len(cases)} drafts labeled in {LABELS_FILE.relative_to(ROOT)}")


def show():
    data = json.loads(CASES_FILE.read_text())
    labels = load_labels()
    where = CASES_FILE.relative_to(ROOT)
    print(f"{where}: {data['count']} drafts, frozen {data['frozen_at']}, sha256 {data['sha256']}")
    for c in data["cases"]:
        score = labels.get(c["case_id"], {}).get("human_score", "-")
        print(f"  {c['case_id']}  human={score}  {c['user_question']}")
    spread = Counter(int(r["human_score"]) for r in labels.values())
    print(f"\n{len(labels)} labels in {LABELS_FILE.relative_to(ROOT)}, spread: " + str(dict(sorted(spread.items()))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["collect", "label", "show"])
    parser.add_argument("--force", action="store_true", help="rebuild eval_cases.json (only before labeling)")
    args = parser.parse_args()
    banner(f"HW10 Part 3.1 eval cases: {args.action}")
    if args.action == "collect":
        asyncio.run(collect(args.force))
    elif args.action == "label":
        label()
    else:
        show()
