# HW10: local GEval judge, qwen2.5:3b through Ollama with a JSON schema reply
import asyncio
import json
import os
import urllib.request

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # no telemetry calls
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "NO")

from deepeval.models import DeepEvalBaseLLM

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen2.5:3b")
JUDGE_SETTINGS = {"temperature": 0.0, "seed": 3319, "num_ctx": 2048, "num_predict": 256}  # same num_ctx as the agents
JUDGE_HTTP_TIMEOUT = float(os.getenv("JUDGE_HTTP_TIMEOUT", "120"))  # seconds per judge call
DEANCHOR = os.getenv("JUDGE_DEANCHOR", "1") == "1"  # remove the score 1 example from the GEval prompt
EXAMPLE = '"reason": "your concise and informative reason here",\n  "score": '  # GEval example answer
ANCHOR = EXAMPLE + "1\n}"
NEUTRAL = EXAMPLE + "<integer from the rubric that fits your reason>\n}"


class LocalJudge(DeepEvalBaseLLM):
    def __init__(self, model=JUDGE_MODEL, base_url=OLLAMA_URL, timeout=JUDGE_HTTP_TIMEOUT, deanchor=DEANCHOR):
        self.model_name, self.base_url, self.timeout = model, base_url.rstrip("/"), timeout
        self.deanchor = deanchor
        super().__init__(model)

    def load_model(self):
        return self.model_name

    def chat(self, prompt, schema=None):
        if self.deanchor:
            prompt = prompt.replace(ANCHOR, NEUTRAL)  # a small judge copies the example score otherwise
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": dict(JUDGE_SETTINGS),
            "format": schema.model_json_schema() if schema else "json",  # Ollama structured output
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("message", {}).get("content", "")

    def generate(self, prompt, schema=None):
        text = self.chat(prompt, schema)
        return schema.model_validate_json(text) if schema else text

    async def a_generate(self, prompt, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)

    def get_model_name(self):
        return f"{self.model_name} (Ollama, local)"


def judge_settings():
    base = {"judge_model": JUDGE_MODEL, "ollama_url": OLLAMA_URL, "http_timeout_s": JUDGE_HTTP_TIMEOUT}
    base["deanchor"] = DEANCHOR
    return {**base, **JUDGE_SETTINGS}
