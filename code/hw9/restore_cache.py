# HW9: put the 10 Part 3 seed answers back into the Redis semantic cache after Redis lost its data
# usage (repo root): python -m code.hw9.restore_cache   (no agents needed; nothing in reports/ is changed)
import json
from code.hw9.p3_sweep import SEEDS_FILE
from code.hw9.qa_service import FixtureQA, qlog
from code.hw9.semantic_cache import normalize
from code.kafka_service.settings import banner
from pathlib import Path

STALE_DEMO = Path(SEEDS_FILE).parent / "p3_stale_demo.json"


def main():
    banner("HW9 restore the semantic cache from the saved seed answers")
    seeds = json.loads(Path(SEEDS_FILE).read_text())
    fresh = json.loads(STALE_DEMO.read_text())["4_invalidated"]  # S01 was re-answered after the Part 3.5 update
    qa = FixtureQA()
    print(f"Cache reset: removed {qa.cache.clear()} cached answers")
    for s in seeds:
        query = s["query"]
        if normalize(query) == normalize(fresh["query"]):
            s = {**s, "answer": fresh["answer"], "data_version": fresh["data_version"]}
            s["correlation_id"] = fresh["correlation_id"]
        current = qa.current_version(s["fixture_codes"]) if s["fixture_codes"] else "none"
        if current != s["data_version"]:
            print(f"SKIP {s['seed']}: saved answer is for {s['data_version']}, MySQL is now {current}")
            continue
        vector = qa.cache.embed_fn(normalize(query))
        key = qa.cache.store(
            query, vector, s["answer"], s["data_version"], s["fixture_codes"], correlation_id=s["correlation_id"]
        )
        qlog("CACHE_RESTORED", s["correlation_id"], seed=s["seed"], key=key, data_version=s["data_version"])
        print(f"restored {s['seed']}  {s['data_version']}")
    print(f"\n{len(qa.cache.entries())} entries in Redis")


if __name__ == "__main__":
    main()
