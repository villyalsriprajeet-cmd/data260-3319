import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.model_client import ModelClient
from schema_hw02 import validate_planner
from agents_graph import parse_and_coerce, PLANNER_SYSTEM
def _planner_call(llm, task, title, content, strict, error_feedback):
    user = f"Task:\n{task}\n\n"
    if error_feedback:
        user += (
            "Your previous answer failed validation with this error:\n"
            f"{error_feedback}\n"
            "Fix it. Remember: exactly 3 tags, each 3-30 characters, "
            "summary 25 words or fewer.\n\n"
        )
    user += "Reply with ONE JSON object only."
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": user},
    ]
    result = llm.complete(messages)
    return parse_and_coerce(result["text"], title, content, strict)
def run_with_retry(title, content, turn_ceiling, email="student@sjsu.edu",
                   strict=False, model="qwen2.5:3b",
                   base_url="http://localhost:11434", temperature=0.0):
    task = (
        f'Fixture title: "{title}". '
        f'Fixture details: "{content}". '
        "Produce exactly 3 topical tags and a one-sentence summary (<=25 words), "
        "in your own words, based only on this fixture."
    )
    llm = ModelClient(model=model, base_url=base_url, temperature=temperature)
    t0 = time.time()
    error_feedback = None
    retries = 0
    proposal = None
    for attempt in range(turn_ceiling):
        proposal = _planner_call(llm, task, title, content, strict, error_feedback)
        data = proposal.get("data", {})
        ok, err = validate_planner({"tags": data.get("tags", []),
                                    "summary": data.get("summary", "")})
        if ok:
            return {
                "valid": True,
                "retries": retries,
                "latency_ms": int((time.time() - t0) * 1000),
                "final": data,
            }
        error_feedback = err
        retries += 1

    return {
        "valid": False,
        "retries": retries,
        "latency_ms": int((time.time() - t0) * 1000),
        "final": (proposal or {}).get("data", {}),
    }