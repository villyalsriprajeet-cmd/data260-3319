# HW9 Part 1 test: 25 views of one fixture, MySQL synced at 10 and 20
# usage (repo root): python -m code.hw9.p1_counter_test [--fixture-id 42] [--views 25]
import argparse
import time
from code.hw9.fixture_cache import SYNC_EVERY, FixtureCache
from code.kafka_service.settings import banner

from sqlalchemy import text


def show_row(cache, fixture_id):
    with cache.engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, fixture_code, views, updated_at FROM fixtures WHERE id = :id"), {"id": fixture_id}
        ).one()
    return dict(row._mapping)


def main(args):
    banner("HW9 Part 1 fixture view counter")
    cache = FixtureCache()
    fid = args.fixture_id
    cache.reset_views(fid)  # start the demo from 0 views
    before = show_row(cache, fid)
    print(f"Fixture {fid} before: {before}")
    print(f"Redis key: {cache.views_key(fid)}\n")
    print("=== Testing Counter ===\n")
    times = []
    for i in range(1, args.views + 1):
        start = time.perf_counter()
        cache.increment_fixture_views(fid, on_count=lambda total, i=i: print(f"Access #{i}: Total = {total}"))
        times.append((time.perf_counter() - start) * 1000)
    after = show_row(cache, fid)
    print(f"\nRedis  {cache.views_key(fid)} = {cache.redis_client.get(cache.views_key(fid))}")
    print(f"MySQL  fixtures.views = {after['views']} (synced at every {SYNC_EVERY} views)")
    print(f"MySQL  updated_at unchanged by the syncs: {after['updated_at'] == before['updated_at']}")
    print(f"Average time per access: {sum(times) / len(times):.2f} ms over {len(times)} accesses")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-id", type=int, default=42)
    parser.add_argument("--views", type=int, default=25)
    main(parser.parse_args())
