# HW10 Step 0: check packages, Ollama, the local GEval judge, Kafka topics, Redis, MySQL and the embedder
# usage (repo root): python -m code.hw10.check_setup
import asyncio
import contextlib
import io
import json
import time
import urllib.request
from code.hw9 import check_setup as hw9
from code.hw10.judge import OLLAMA_URL, LocalJudge, judge_settings
from code.kafka_service.settings import PREFIX, banner
from importlib.metadata import PackageNotFoundError, version

from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.test_case import LLMTestCase, SingleTurnParams

TOPICS = ["inbox", "tasks", "drafts", "final", "dead_letter", "evaluations"]
SMOKE_RUBRIC = [
    Rubric(score_range=(1, 1), expected_outcome="Wrong or unrelated answer."),
    Rubric(score_range=(3, 3), expected_outcome="Partly correct answer."),
    Rubric(score_range=(5, 5), expected_outcome="Correct and complete answer."),
]


def installed(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def check_packages():
    found = {p: installed(p) for p in ("deepeval", "streamlit", "numpy", "torch", "sentence-transformers")}
    ok = found["deepeval"] == "4.3.4" and found["streamlit"] == "1.67.0"
    hw9.show("Python packages", ok, found)


def check_ollama_version():
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=10) as resp:
        ver = json.loads(resp.read())["version"]
    major, minor = (int(x) for x in ver.split(".")[:2])
    hw9.show("Ollama 0.5 or newer (JSON schema)", (major, minor) >= (0, 5), f"version {ver}")


def check_judge():
    metric = GEval(
        name="Smoke-Test",
        evaluation_steps=["Check whether the actual output correctly answers the input."],
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        rubric=SMOKE_RUBRIC,
        model=LocalJudge(),
        async_mode=False,
    )
    case = LLMTestCase(
        input="Fixture FX-00042 is at Milpitas Field. Where is fixture FX-00042 played?",
        actual_output="Fixture FX-00042 is played at Milpitas Field.",
    )
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):  # hide deepeval spinner
        metric.measure(case)
    ms = (time.perf_counter() - t0) * 1000
    raw = round(1 + 4 * metric.score, 2)  # GEval reports (score - 1) / 4 for a 1 to 5 rubric
    hw9.show("GEval with the local judge", 1 <= raw <= 5, f"score {raw}/5 in {ms:.0f} ms, reason: {metric.reason}")


def check_topics():
    have = set(asyncio.run(hw9.kafka_topics()))
    need = [f"{PREFIX}_{t}" for t in TOPICS]
    missing = [t for t in need if t not in have]
    hw9.show("Kafka HW8 and HW10 topics", not missing, f"missing: {missing}" if missing else f"all {len(need)} found")


if __name__ == "__main__":
    banner("HW10 Step 0 setup check")
    print(f"Judge settings: {judge_settings()}", flush=True)
    steps = [
        ("Packages", check_packages),
        ("Ollama", hw9.check_ollama),
        ("Ollama version", check_ollama_version),
        ("Judge", check_judge),
        ("Kafka", check_topics),
        ("Redis", hw9.check_redis),
        ("MySQL", hw9.check_mysql),
        ("Embedder", hw9.check_embedder),
    ]
    for name, fn in steps:
        try:
            fn()
        except Exception as exc:  # report and keep checking the rest
            hw9.show(name, False, f"{type(exc).__name__}: {exc}")
    print(f"\n{sum(hw9.RESULTS)}/{len(hw9.RESULTS)} checks passed", flush=True)
