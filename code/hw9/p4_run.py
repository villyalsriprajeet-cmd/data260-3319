# HW9 Part 4 runner (qwen2.5:3b through Ollama, no Kafka needed)
# usage (repo root), in this order:
#   python -m code.hw9.p4_run reference     export the ground-truth facts from MySQL s3319_rel
#   python -m code.hw9.p4_run demo-repair   4.1 controlled case: bad first answer, feedback, revised answer
#   python -m code.hw9.p4_run train         4.1 + 4.2 on training_data.json: repair, create and reuse lessons
#   python -m code.hw9.p4_run validate      4.3 keep a lesson only if validation_data.json does not get worse
#   python -m code.hw9.p4_run test          4.4 the four variants on test_data.json
import argparse
import asyncio
import csv
import json
import re
import shutil
from code.hw9.p4_agents import (
    CANDIDATES_FILE,
    LESSONS_FILE,
    PART4,
    REFERENCE_FILE,
    TITLE_RE,
    AnsweringAgent,
    EvaluatorAgent,
    LessonStore,
    analyze,
    load_json,
    load_reference,
    solve,
)
from code.hw9.qa_service import fixture_codes
from code.kafka_service.settings import banner, now_utc

from sqlalchemy import bindparam, text

DATASETS = {name: PART4 / f"{name}_data.json" for name in ("training", "validation", "test")}
RUNS = PART4 / "runs"
REF_SQL = text(
    "SELECT f.fixture_code, f.fixture_title, f.venue, f.tickets_available, t.name AS home_team, "
    "t.city AS home_city FROM fixtures f JOIN teams t ON t.id = f.home_team_id WHERE f.fixture_code IN :codes"
).bindparams(bindparam("codes", expanding=True))
DEMO_QUESTION = ("TR06", "What is the venue of fixture FX-01104 and how many tickets are left?")


def engine():
    from code.api.database import engine as eng

    return eng


def questions(name):
    return load_json(DATASETS[name])


def save_run(name, results):
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))


def reference(args):
    banner("HW9 Part 4 build the reference dataset from MySQL s3319_rel")
    codes = sorted({c for name in DATASETS for q in questions(name) for c in fixture_codes(q["question"])})
    with engine().connect() as conn:
        rows = {r.fixture_code: dict(r._mapping) for r in conn.execute(REF_SQL, {"codes": codes})}
    fixtures, problems = [], []
    for code in codes:
        if code not in rows:
            continue
        r = rows[code]
        m = TITLE_RE.match(r["fixture_title"])
        if not m or m["home"] != r["home_team"]:
            problems.append(f"{code}: title '{r['fixture_title']}' does not start with home team '{r['home_team']}'")
            continue
        fixtures.append({**r, "away_team": m["away"], "matchweek": int(m["week"])})
    if problems:  # never write a reference with gaps: a skipped fixture would look like an unknown code
        raise SystemExit("PROBLEMS, nothing written (send these lines to fix the codes):\n  " + "\n  ".join(problems))
    missing = [c for c in codes if c not in rows]
    data = {
        "source": "MySQL s3319_rel (fixtures JOIN teams), exported by code/hw9/p4_run.py reference",
        "exported_at": now_utc(),
        "fields": "title is 'Home vs Away - Matchweek N'; away_team and matchweek come from the title",
        "fixtures": fixtures,
        "not_in_league": missing,
    }
    REFERENCE_FILE.write_text(json.dumps(data, indent=2) + "\n")
    print(f"{len(fixtures)} fixtures exported, {len(missing)} codes not in the league: {', '.join(missing)}")
    for f in fixtures:
        print(
            f"  {f['fixture_code']}  tickets={f['tickets_available']:<4} home={f['home_team']:<22} "
            f"away={f['away_team']:<22} week={f['matchweek']:<3} venue={f['venue']}"
        )
    fx, _ = load_reference()
    print("\nWhat each question asks (kind / fields):")
    for name in DATASETS:
        for q in questions(name):
            info = analyze(q["question"], fx)
            print(f"  {q['id']}  {info['kind']:<16} {','.join(info['fields']):<22} {q['question']}")
    banner("end of reference export")


async def demo_repair(args):
    banner("HW9 Part 4.1 controlled revision: the first answer is made incomplete on purpose")
    fx, _ = load_reference()
    qid, question = DEMO_QUESTION
    print(f"Question ({qid}): {question}\n")
    res = await solve(qid, question, AnsweringAgent(engine()), EvaluatorAgent(fx), repair=True, inject_fault=True)
    print(f"\nAttempts: {res['n_attempts']}   final evaluation: {res['final_result']}   latency: {res['latency_s']} s")
    print(f"Final response: {res['final_answer']}")
    save_run("demo_repair", [res])
    banner("end of controlled revision")


async def run_set(name, items, answerer, evaluator, store, repair):
    results = []
    for q in items:
        results.append(await solve(q["id"], q["question"], answerer, evaluator, store=store, repair=repair))
    return results


async def train(args):
    banner("HW9 Part 4.1/4.2 training run: evaluator repair + lessons from repeated failures")
    fx, _ = load_reference()
    LESSONS_FILE.unlink(missing_ok=True)  # start the lesson memory empty
    store = LessonStore(LESSONS_FILE, learn=True)
    results = await run_set(
        "training", questions("training"), AnsweringAgent(engine()), EvaluatorAgent(fx), store, True
    )
    shutil.copy(LESSONS_FILE, CANDIDATES_FILE) if LESSONS_FILE.exists() else CANDIDATES_FILE.write_text("[]\n")
    save_run("training", results)
    print(f"\nFailure patterns seen on first attempts: { {k: v for k, v in store.seen.items()} }")
    print(f"Lessons created: {len(store.lessons)} (saved to lessons.json and lessons_candidates.json)")
    for lsn in store.lessons:
        print(f"  {lsn['lesson_id']}  use_count={lsn['use_count']}  {lsn['failure_pattern']}")
    reused = [r for r in results if r["lessons_used"]]
    print(f"Questions that loaded an earlier lesson: {', '.join(r['id'] for r in reused) or 'none'}")
    summary(results)
    banner("end of training run")


def summary(results):
    ok = sum(r["final_result"] == "PASS" for r in results)
    first = sum(r["first_result"] == "PASS" for r in results)
    print(f"First-attempt PASS {first}/{len(results)}, final PASS {ok}/{len(results)}")


async def validate(args):
    banner("HW9 Part 4.3 validate each lesson on validation_data.json before keeping it")
    fx, _ = load_reference()
    candidates = load_json(CANDIDATES_FILE, [])
    items, answerer, evaluator = questions("validation"), AnsweringAgent(engine()), EvaluatorAgent(fx)
    unrelated = {q["id"] for q in items if analyze(q["question"], fx)["kind"] in ("unknown_fixture", "unsupported")}

    async def first_try(lessons):
        res = await run_set("validation", items, answerer, evaluator, LessonStore(lessons=lessons), repair=False)
        return {r["id"]: r for r in res}

    print("Run 0: no lessons")
    base = await first_try([])
    kept, rejected, report = [], [], []
    for lsn in candidates:
        print(f"\nRun with {lsn['lesson_id']} only: {lsn['failure_pattern']}")
        trial = await first_try([dict(lsn)])
        b = {q: r["first_result"] == "PASS" for q, r in base.items()}
        t = {q: r["first_result"] == "PASS" for q, r in trial.items()}
        fails_before, fails_after = sum(not v for v in b.values()), sum(not v for v in t.values())
        broke = [q for q in b if b[q] and not t[q]]
        fixed = [q for q in b if not b[q] and t[q]]
        unsupported_after = [q for q in unrelated if not t[q]]
        unsupported_before = [q for q in unrelated if not b[q]]
        checks = {
            "failure cases improve or stay the same": fails_after <= fails_before,
            "previously correct answers stay correct": not broke,
            "unrelated questions get no unsupported answers": len(unsupported_after) <= len(unsupported_before),
        }
        keep = all(checks.values())
        row = {
            "lesson_id": lsn["lesson_id"],
            "failures_before": fails_before,
            "failures_after": fails_after,
            "fixed": fixed,
            "broke": broke,
            "unrelated_unsupported_after": unsupported_after,
            "checks": checks,
            "decision": "keep" if keep else "remove",
        }
        report.append(row)
        print(f"  failures {fails_before} -> {fails_after}, fixed {fixed or '-'}, broke {broke or '-'}")
        for name, ok in checks.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        print(f"  decision: {row['decision'].upper()}")
        (kept if keep else rejected).append({**lsn, "validated_at": now_utc(), "validation": row})
    LESSONS_FILE.write_text(json.dumps(kept, indent=2) + "\n")
    (PART4 / "lessons_rejected.json").write_text(json.dumps(rejected, indent=2) + "\n")
    (PART4 / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nKept in lessons.json: {[x['lesson_id'] for x in kept] or 'none'}")
    print(f"Removed (lessons_rejected.json): {[x['lesson_id'] for x in rejected] or 'none'}")
    if kept:
        combined = await first_try([dict(x) for x in kept])
        together = sum(r["first_result"] == "PASS" for r in combined.values())
        alone = sum(r["first_result"] == "PASS" for r in base.values())
        print(
            f"All kept lessons together: first-attempt PASS {together}/{len(items)} (no lessons: {alone}/{len(items)})"
        )
    banner("end of validation")


async def test(args):
    banner("HW9 Part 4.4 four variants on test_data.json (same test set for every variant)")
    fx, _ = load_reference()
    items, answerer, evaluator = questions("test"), AnsweringAgent(engine()), EvaluatorAgent(fx)
    variants = [
        ("Baseline", None, False),
        ("Evaluator Repair", None, True),
        ("Lesson Memory", LessonStore(CANDIDATES_FILE), True),
        ("Validated Improvement", LessonStore(LESSONS_FILE), True),
    ]
    table = []
    for name, store, repair in variants:
        print(f"\n=== {name} ===")
        res = await run_set("test", items, answerer, evaluator, store, repair)
        save_run("test_" + re.sub(r"\W+", "_", name.lower()), res)
        n = len(res)
        table.append(
            {
                "variant": name,
                "correct": sum(r["final_result"] == "PASS" for r in res),
                "incorrect": sum(r["final_result"] != "PASS" for r in res),
                "avg_attempts": round(sum(r["n_attempts"] for r in res) / n, 2),
                "avg_latency_s": round(sum(r["latency_s"] for r in res) / n, 2),
                "first_attempt_correct": sum(r["first_result"] == "PASS" for r in res),
                "lessons_available": len(store.lessons) if store else 0,
                "failed": [r["id"] for r in res if r["final_result"] != "PASS"],
            }
        )
    (PART4 / "results_test.json").write_text(json.dumps(table, indent=2) + "\n")
    with open(PART4 / "results_test.csv", "w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=list(table[0]))
        out.writeheader()
        out.writerows(table)
    print("\nVariant                Correct  Incorrect  Avg attempts  Avg latency (s)  Lessons  Still wrong")
    for t in table:
        print(
            f"{t['variant']:<22} {t['correct']:>3}/{len(items):<4} {t['incorrect']:>5}      {t['avg_attempts']:>6}"
            f"        {t['avg_latency_s']:>8}       {t['lessons_available']:>4}     {', '.join(t['failed']) or '-'}"
        )
    banner("end of test run")


if __name__ == "__main__":
    commands = {"reference": reference, "demo-repair": demo_repair, "train": train, "validate": validate, "test": test}
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=list(commands))
    args = parser.parse_args()
    fn = commands[args.command]
    asyncio.run(fn(args)) if asyncio.iscoroutinefunction(fn) else fn(args)
