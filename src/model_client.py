import json
import urllib.request


class ModelClient:
    def __init__(
        self,
        model="qwen2.5:3b",
        base_url="http://localhost:11434",
        temperature=0.0,
        num_ctx=512,
        num_predict=256,
        seed=None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.seed = seed  # fixed seed for repeatable runs

    def complete(self, messages, tools=None, json_mode=True):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if json_mode:
            payload["format"] = "json"
        if self.seed is not None:
            payload["options"]["seed"] = self.seed
        if tools:
            payload["tools"] = tools
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body.get("message", {}).get("content", "")
        tool_calls = body.get("message", {}).get("tool_calls") or []  # HW7: native tool calls
        input_tokens = body.get("prompt_eval_count", 0)
        output_tokens = body.get("eval_count", 0)
        return {
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "tool_calls": tool_calls,
        }
