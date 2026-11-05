# HW9 Part 1: Redis-backed view counter for fixtures, synced to MySQL s3319_rel every 10 views
import os
import time
from code.kafka_service.settings import PREFIX

import redis
from sqlalchemy import text

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SYNC_EVERY = 10  # persist the count to MySQL every 10 views


def make_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


class FixtureCache:
    def __init__(self, redis_client=None, engine=None):
        self.redis_client = redis_client or make_redis()
        if engine is None:
            from code.api.database import engine  # MySQL s3319_rel from code/api/.env
        self.engine = engine

    def views_key(self, fixture_id):
        return f"{PREFIX}:views:fixture:{fixture_id}"

    def db_views(self, fixture_id):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT views FROM fixtures WHERE id = :id"), {"id": fixture_id}).scalar()

    def increment_fixture_views(self, fixture_id, on_count=None):
        key = self.views_key(fixture_id)
        if not self.redis_client.exists(key):  # first view since Redis started: begin from the saved count
            saved = self.db_views(fixture_id)
            if saved is None:
                raise ValueError(f"Fixture {fixture_id} not found")
            self.redis_client.set(key, saved, nx=True)  # nx: never overwrite a count another process set
        count = self.redis_client.incr(key)  # atomic +1 in Redis, no database query
        if on_count:
            on_count(count)  # lets the caller print the access before the sync message
        if count % SYNC_EVERY == 0:
            self.sync_views_to_db(fixture_id, count)
        return count

    def sync_views_to_db(self, fixture_id, count):
        start = time.perf_counter()
        with self.engine.begin() as conn:
            conn.execute(
                # updated_at = updated_at keeps the row's data version, a view is not a data change
                text("UPDATE fixtures SET views = :views, updated_at = updated_at WHERE id = :id"),
                {"views": count, "id": fixture_id},
            )
        ms = (time.perf_counter() - start) * 1000
        print(f"✓ Synced views to database (fixture {fixture_id}, views = {count}, {ms:.1f} ms)", flush=True)

    def reset_views(self, fixture_id):
        self.redis_client.delete(self.views_key(fixture_id))
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE fixtures SET views = 0, updated_at = updated_at WHERE id = :id"), {"id": fixture_id}
            )
