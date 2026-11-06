# HW9 Part 3.5: a stale cached answer after a s3319_rel update, then invalidation with the data-version marker
# usage (repo root, the 3 HW8 agents running, the 10 seeds cached):
#   python -m code.hw9.p3_stale [--new-tickets 12]
import argparse
import asyncio
import json
import statistics
import time
from code.hw9.p3_cases import load_cases
from code.hw9.p3_sweep import RAW
from code.hw9.qa_service import FixtureQA, qlog
from code.kafka_service.settings import banner

from sqlalchemy import text

CODE = "FX-00042"  # seed S01 asks for this fixture's ticket count
SHIP_THRESHOLD = 0.95  # chosen in Part 3.4
ROW_SQL = text("SELECT fixture_code, tickets_available, updated_at FROM fixtures WHERE fixture_code = :c")


def db_row(qa):
    with qa.engine.connect() as conn:
        row = dict(conn.execute(ROW_SQL, {"c": CODE}).one()._mapping)
    return {**row, "updated_at": row["updated_at"].isoformat()}


async def ask(qa, query, step):
    res = await qa.handle_query(query)
    print(
        f"[{step}] is_cached={res['is_cached']}  similarity={res['similarity']}  latency={res['latency_ms']} ms"
        f"  data_version={res['data_version']}\n      answer: {res['answer']}",
        flush=True,
    )
    return res


async def main(args):
    banner("HW9 Part 3.5 stale answer and invalidation (data-version marker)")
    seeds, _ = load_cases()
    query = seeds["S01"]
    qa = FixtureQA(threshold=SHIP_THRESHOLD, check_version=False)
    await qa.start()
    log = {"query": query, "fixture_code": CODE, "threshold": SHIP_THRESHOLD}
    try:
        before = db_row(qa)
        print(f"Question (seed S01): {query}")
        print(f"MySQL before: {before}\n")
        print("=== 1. Version check OFF: the cached answer is served ===")
        log["1_before_update"] = await ask(qa, query, "1")

        new = args.new_tickets if args.new_tickets != before["tickets_available"] else args.new_tickets + 1
        with qa.engine.begin() as conn:  # a real data change: tickets were sold, updated_at moves
            conn.execute(
                text("UPDATE fixtures SET tickets_available = :t WHERE fixture_code = :c"), {"t": new, "c": CODE}
            )
        after = db_row(qa)
        qlog("RECORD_UPDATED", fixture=CODE, tickets_before=before["tickets_available"], tickets_after=new)
        print(f"\n=== 2. UPDATE fixtures SET tickets_available = {new} WHERE fixture_code = '{CODE}' ===")
        print(f"MySQL after:  {after}\n")

        print("=== 3. Version check OFF: STALE hit ===")
        stale = await ask(qa, query, "3")
        current = qa.current_version([CODE])
        print(f"      cached data_version : {stale['data_version']}")
        print(f"      current data_version: {current}")
        print(f"      STALE: the cache still answers with the old count, MySQL now has {new} tickets")
        log["3_stale_hit"] = {**stale, "current_version": current, "db_tickets": new}

        print("\n=== 4. Version check ON: marker differs -> invalidate, rerun the agents ===")
        qa.check_version = True
        log["4_invalidated"] = await ask(qa, query, "4")

        print("\n=== 5. Version check ON, same question again: fresh answer from the cache ===")
        log["5_fresh_hit"] = await ask(qa, query, "5")

        times = []
        for _ in range(50):  # the price of the strategy: one indexed MySQL read on every hit
            start = time.perf_counter()
            qa.current_version([CODE])
            times.append((time.perf_counter() - start) * 1000)
        log["version_check_ms"] = {
            "mean": round(statistics.mean(times), 2),
            "median": round(statistics.median(times), 2),
            "max": round(max(times), 2),
        }
        print(f"\nCost of the check on every hit (50 runs): {log['version_check_ms']}")
    finally:
        await qa.stop()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "p3_stale_demo.json").write_text(json.dumps(log, indent=2, default=str) + "\n")
    banner("end of stale answer demo")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-tickets", type=int, default=12)
    asyncio.run(main(parser.parse_args()))
