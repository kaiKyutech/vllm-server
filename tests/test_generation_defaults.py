import asyncio
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generation_defaults import apply_defaults, GenerationDefaultsMiddleware


ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "configs/generation/Qwen3.5-9B.json").read_text())


class DefaultsTests(unittest.TestCase):
    def test_official_thinking_is_preserved(self):
        body = {"messages": [{"role": "user", "content": "test"}]}
        result = apply_defaults(body, PROFILE)
        self.assertEqual(result["temperature"], 1.0)
        self.assertEqual(result["presence_penalty"], 1.5)
        self.assertNotIn("chat_template_kwargs", result)
        self.assertEqual(body, {"messages": [{"role": "user", "content": "test"}]})

    def test_non_thinking_recommendations(self):
        result = apply_defaults({"chat_template_kwargs": {"enable_thinking": False}}, PROFILE)
        self.assertEqual(result["temperature"], 0.7)
        self.assertEqual(result["top_p"], 0.8)
        self.assertEqual(result["top_k"], 20)
        self.assertFalse(result["chat_template_kwargs"]["enable_thinking"])

    def test_explicit_zero_and_client_values_win(self):
        body = {"temperature": 0, "presence_penalty": 0, "top_k": 0,
                "top_p": 0.5, "seed": 7, "max_tokens": 99}
        result = apply_defaults(body, PROFILE)
        for key, value in body.items():
            self.assertEqual(result[key], value)

    def test_null_falls_back_and_server_overrides_win_over_profile(self):
        profile = copy.deepcopy(PROFILE)
        profile["server_overrides"] = {"temperature": 0.25, "presence_penalty": 0.75}
        result = apply_defaults({"temperature": None}, profile)
        self.assertEqual(result["temperature"], 0.25)
        self.assertEqual(result["presence_penalty"], 0.75)


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, raw, path="/v1/chat/completions"):
        import os
        from unittest.mock import patch
        messages = [
            {"type": "http.request", "body": raw[:5], "more_body": True},
            {"type": "http.request", "body": raw[5:], "more_body": False},
        ]
        seen = {}

        async def receive():
            return messages.pop(0)

        async def app(scope, receive, send):
            chunks = []
            while True:
                msg = await receive()
                chunks.append(msg["body"])
                if not msg.get("more_body", False):
                    break
            seen["body"] = b"".join(chunks)
            seen["headers"] = dict(scope["headers"])

        async def send(message):
            pass

        with patch.dict(os.environ, {"VLLM_SERVER_GENERATION_DEFAULTS": json.dumps(PROFILE)}):
            middleware = GenerationDefaultsMiddleware(app)
        scope = {"type": "http", "method": "POST", "path": path,
                 "headers": [(b"content-length", str(len(raw)).encode()),
                             (b"authorization", b"Bearer private-test-key")]}
        await middleware(scope, receive, send)
        return seen

    async def test_chunked_unicode_body_and_headers(self):
        raw = json.dumps({"messages": [{"role": "user", "content": "こんにちは"}]},
                         ensure_ascii=False).encode()
        result = await self.invoke(raw)
        body = json.loads(result["body"])
        self.assertEqual(body["messages"][0]["content"], "こんにちは")
        self.assertEqual(body["presence_penalty"], 1.5)
        self.assertEqual(int(result["headers"][b"content-length"]), len(result["body"]))
        self.assertEqual(result["headers"][b"authorization"], b"Bearer private-test-key")

    async def test_invalid_json_is_left_for_api_validation(self):
        raw = b'{"messages": broken}'
        self.assertEqual((await self.invoke(raw))["body"], raw)

    async def test_other_routes_are_untouched(self):
        raw = b'{"messages": []}'
        self.assertEqual((await self.invoke(raw, "/other"))["body"], raw)


if __name__ == "__main__":
    unittest.main()
