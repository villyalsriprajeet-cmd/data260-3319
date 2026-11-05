# HW9 Part 3.1: load and check reports/hw09/cache_cases.yaml (shared by the sweep)
# usage (repo root): python -m code.hw9.p3_cases
from code.kafka_service.settings import banner
from collections import Counter
from pathlib import Path

import yaml

CASES_FILE = Path(__file__).resolve().parents[2] / "reports" / "hw09" / "cache_cases.yaml"
CATEGORIES = {"exact_duplicate": "hit", "paraphrase": "hit", "similar_different": "miss", "unrelated": "miss"}


def load_cases(path=CASES_FILE):
    data = yaml.safe_load(Path(path).read_text())
    seeds = {s["id"]: s["query"] for s in data["seeds"]}
    cases = data["cases"]
    problems = []
    if len(seeds) != 10:
        problems.append(f"expected 10 seeds, found {len(seeds)}")
    if len(cases) != 40 or len({c["id"] for c in cases}) != 40:
        problems.append(f"expected 40 cases with unique ids, found {len(cases)}")
    counts = Counter(c["category"] for c in cases)
    for cat, expected in CATEGORIES.items():
        if counts[cat] != 10:
            problems.append(f"{cat}: expected 10 cases, found {counts[cat]}")
    for c in cases:
        if CATEGORIES.get(c["category"]) != c["expected"]:
            problems.append(f"{c['id']}: category {c['category']} must expect {CATEGORIES.get(c['category'])}")
        if c["category"] != "unrelated" and c["ref"] not in seeds:
            problems.append(f"{c['id']}: ref {c['ref']} is not a seed")
        if c["category"] == "exact_duplicate" and c["query"] != seeds.get(c["ref"]):
            problems.append(f"{c['id']}: exact duplicate text differs from {c['ref']}")
        if c["category"] != "exact_duplicate" and c["query"] in seeds.values():
            problems.append(f"{c['id']}: same text as a seed but not labeled exact_duplicate")
    if problems:
        raise ValueError("cache_cases.yaml problems:\n" + "\n".join(problems))
    return seeds, cases


if __name__ == "__main__":
    banner("HW9 Part 3.1 cache_cases.yaml check")
    seeds, cases = load_cases()
    print(f"File: {CASES_FILE.relative_to(CASES_FILE.parents[2])}")
    print(f"Seeds (cached before the sweep): {len(seeds)}")
    counts = Counter((c["category"], c["expected"]) for c in cases)
    for (cat, exp), n in sorted(counts.items()):
        print(f"  {cat:<18} expected {exp:<4}  {n} cases")
    print(f"Total cases: {len(cases)}  - all checks passed\n")
    for c in cases:
        print(f"{c['id']}  {c['category']:<18} {c['expected']:<4} ref={str(c['ref']):<4}  {c['query']}")
