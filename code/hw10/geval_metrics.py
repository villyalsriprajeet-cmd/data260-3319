# HW10 Part 2: GEval criteria on one 1 to 5 rubric, scored by the local judge with a time limit
import asyncio
import time
from code.hw10.judge import JUDGE_HTTP_TIMEOUT, LocalJudge

from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.test_case import LLMTestCase, SingleTurnParams

METRIC_TIMEOUT = JUDGE_HTTP_TIMEOUT + 30  # seconds before one judge score is abandoned
PARAMS = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]

HELPFULNESS_STEPS = [
    "Check whether the actual output directly answers the question in the input.",
    "Check that every fact in the actual output (fixture codes, venues, ticket counts, team names, dates, times) "
    "agrees with the facts given in the input; an invented or contradicting fact is a serious error.",
    "Check that the advice is specific and useful for a community sports league manager, player or fan, "
    "not generic filler.",
    "Penalize missing key information, unnecessary tangents, or text that is hard to follow.",
]
HELPFULNESS_LEVELS = [
    "Does not answer the question, or is mostly wrong or invented.",
    "Partly answers, but has a wrong or invented fact or misses most of what was asked.",
    "Answers the main question correctly but is vague, incomplete or padded.",
    "Correct and useful, with a small omission or minor wording issue.",
    "Correct, complete, specific and concise.",
]
PLAN_STEPS = [
    "Check whether the steps in the actual output, taken together, would lead to a complete answer to the input.",
    "Check that each step is concrete and specific to the fixture question in the input, not generic filler.",
    "Check that the steps rely only on facts given in the input and do not need invented dates, scores or names.",
    "Penalize steps that are redundant, out of order, or unrelated to the question.",
]
PLAN_LEVELS = [
    "The plan is missing, unrelated, or would lead to a wrong answer.",
    "The plan touches the question but misses most of what is needed.",
    "The plan covers the main need but has vague, redundant or missing steps.",
    "The plan is clear and relevant with one minor gap or vague step.",
    "The plan is concrete, complete, well ordered and uses only the given facts.",
]
CRITERIA = {
    "plan_quality": ("Plan-Quality", PLAN_STEPS, PLAN_LEVELS),
    "helpfulness": ("Helpfulness", HELPFULNESS_STEPS, HELPFULNESS_LEVELS),
}


def rubric(levels):
    return [Rubric(score_range=(i, i), expected_outcome=text) for i, text in enumerate(levels, 1)]  # 1 to 5


def make_metric(criterion, judge):
    name, steps, levels = CRITERIA[criterion]
    return GEval(
        name=name,
        evaluation_steps=steps,
        evaluation_params=PARAMS,
        rubric=rubric(levels),
        model=judge,
        async_mode=False,
        verbose_mode=False,
    )


def measure(criterion, question, output, judge):
    metric = make_metric(criterion, judge)  # a new metric per call, so no state is shared
    metric.measure(LLMTestCase(input=question, actual_output=output), _show_indicator=False)  # no spinner
    return round(1 + 4 * metric.score, 2), (metric.reason or "").strip()  # back to the 1 to 5 scale


async def score(criterion, question, output, judge=None, timeout=METRIC_TIMEOUT):
    t0 = time.perf_counter()
    result = {"criterion": criterion, "score": None, "reason": None, "status": "ok", "error": None}
    try:
        if not isinstance(output, str) or not output.strip():
            raise ValueError("nothing to score (empty text)")
        job = asyncio.to_thread(measure, criterion, question, output, judge or LocalJudge())
        result["score"], result["reason"] = await asyncio.wait_for(job, timeout=timeout)
    except Exception as exc:  # judge down or silent, bad JSON or empty input: record it, never hang
        detail = str(exc) or f"no judge score within {timeout:.0f} s"  # the outer limit has no message
        result.update(status="error", error=f"{type(exc).__name__}: {detail}")
    result["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result
