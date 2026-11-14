# HW10 Part 2: judge calibration probe, known good and bad outputs scored with and without the score 1 example
# usage (repo root): python -m code.hw10.judge_probe
import asyncio
import json
from code.hw10.geval_metrics import score
from code.hw10.judge import LocalJudge
from code.hw10.traced_qa import ROOT
from code.kafka_service.settings import banner

OUT_FILE = ROOT / "reports" / "hw10" / "eval" / "judge_probe.json"
QUESTION = (
    "How many tickets are still available for fixture FX-00305, and where is it being played?\n\n"
    "Fixture facts from the league database s3319_rel (use these exact values):\n"
    '- FX-00305: title "Berkeley Spartans vs Morgan Hill Falcons - Matchweek 7", venue Berkeley Field, '
    "tickets_available 263, home team Berkeley Spartans (Berkeley)"
)
ITEMS = [
    (
        "helpfulness",
        "correct answer",
        "high (4-5)",
        "Fixture FX-00305, also known as Berkeley Spartans vs Morgan Hill Falcons - Matchweek 7, is being played at "
        "Berkeley Field. There are 263 tickets still available for this fixture.",
    ),
    (
        "helpfulness",
        "wrong facts",
        "low (1-2)",
        "Fixture FX-00305 is being played at Milpitas Field. There are 51 tickets still available.",
    ),
    (
        "helpfulness",
        "off topic",
        "lowest (1)",
        "Players should arrive about 30 minutes before kickoff so they have time to warm up.",
    ),
    (
        "plan_quality",
        "concrete plan",
        "high (4-5)",
        "1. Read the tickets_available value for FX-00305 from the given facts.\n"
        "2. Read the venue of FX-00305 from the given facts.\n"
        "3. Answer with both values in one short sentence.",
    ),
    ("plan_quality", "vague plan", "low (1-2)", "1. Read the question.\n2. Think about it.\n3. Write an answer."),
]


async def main():
    banner("HW10 Part 2 judge calibration probe (qwen2.5:3b, same steps and rubric)")
    rows = []
    for deanchor in (False, True):
        judge = LocalJudge(deanchor=deanchor)
        prompt = "de-anchored example" if deanchor else "original GEval example (score 1)"
        print(f"\n{prompt}")
        for criterion, label, expected, text in ITEMS:
            res = await score(criterion, QUESTION, text, judge)
            rows.append({"prompt": prompt, "criterion": criterion, "item": label, "expected": expected, **res})
            why = res["reason"] or res["error"]
            print(f"  {criterion:<12} {label:<15} expected {expected:<11} score={res['score']}  {why}")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"\nsaved {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
