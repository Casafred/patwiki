import json
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from app.ai.fields.engine import AIFieldEngine
from app.services.llm_service import (
    DEEPSEEK_FLASH_MODEL,
    LLMConfig,
    chat_completion,
    normalize_base_url,
    normalize_model,
)


class _FakeClient:
    responses = []
    requests = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, *, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)


class LLMServiceTest(unittest.TestCase):
    def setUp(self):
        _FakeClient.responses = []
        _FakeClient.requests = []
        self.config = LLMConfig(
            provider="deepseek",
            api_key="test-key",
            model=DEEPSEEK_FLASH_MODEL,
            base_url="https://api.deepseek.com",
            thinking_mode="enabled",
            reasoning_effort="low",
        )

    def test_deepseek_v4_payload_and_response_metadata(self):
        _FakeClient.responses = [httpx.Response(200, json={
            "model": "deepseek-v4-flash-0731",
            "choices": [{"finish_reason": "stop", "message": {
                "content": "{\\\"result\\\": \\\"ok\\\"}",
                "reasoning_content": "reasoning trace",
            }}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        })]
        with patch("app.services.llm_service.httpx.Client", _FakeClient):
            result = chat_completion("return JSON", self.config, retries=0, response_format={"type": "json_object"})

        request = _FakeClient.requests[0]
        self.assertEqual(request["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(request["json"]["model"], DEEPSEEK_FLASH_MODEL)
        self.assertEqual(request["json"]["thinking"], {"type": "enabled"})
        self.assertEqual(request["json"]["reasoning_effort"], "low")
        self.assertEqual(request["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(result["reasoning_content"], "reasoning trace")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["usage"]["prompt_tokens"], 12)

    def test_documented_deepseek_alias_and_base_url_normalize(self):
        self.assertEqual(normalize_model("deepseek", "v4flash"), DEEPSEEK_FLASH_MODEL)
        self.assertEqual(normalize_base_url("https://api.deepseek.com/chat/completions/"), "https://api.deepseek.com")

    def test_rate_limit_is_retried_once(self):
        _FakeClient.responses = [
            httpx.Response(429, headers={"Retry-After": "0"}, text="rate limited"),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
        with patch("app.services.llm_service.httpx.Client", _FakeClient), patch("app.services.llm_service.time.sleep"):
            result = chat_completion("ping", self.config, retries=1)
        self.assertEqual(result["content"], "ok")
        self.assertEqual(len(_FakeClient.requests), 2)


class _ConcurrentLLM:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def invoke(self, prompt, **_kwargs):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        return type("Response", (), {"content": prompt, "response_model": "test"})()


class AIConcurrencyTest(unittest.TestCase):
    def test_network_batch_respects_configured_concurrency(self):
        llm = _ConcurrentLLM()
        engine = AIFieldEngine(None)
        with patch.object(engine, "_get_llm", return_value=(llm, "test")), patch.object(engine, "_batch_concurrency", return_value=2):
            results = engine._run_network_batch({1: "a", 2: "b", 3: "c", 4: "d"})
        self.assertEqual(set(results), {1, 2, 3, 4})
        self.assertEqual(llm.max_active, 2)


if __name__ == "__main__":
    unittest.main()
