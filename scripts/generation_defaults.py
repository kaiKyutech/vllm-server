"""vLLM標準のASGIミドルウェア拡張。省略された生成パラメータだけ補う。"""
import json
import logging
import os
from pathlib import Path


def apply_defaults(payload, profile):
    if not isinstance(payload, dict):
        return payload
    defaults = dict(profile.get("defaults", {}))
    kwargs = payload.get("chat_template_kwargs")
    thinking = kwargs.get("enable_thinking") if isinstance(kwargs, dict) else None
    if thinking is None:
        thinking = profile.get("official_thinking_default")
    if isinstance(thinking, bool):
        mode = "thinking" if thinking else "non_thinking"
        defaults.update(profile.get("modes", {}).get(mode, {}))
    defaults.update(profile.get("server_overrides", {}))
    result = dict(payload)
    for key, value in defaults.items():
        if result.get(key) is None:
            result[key] = value
    # thinking自体は注入しない。省略時はモデルの公式テンプレートに任せる。
    return result


class GenerationDefaultsMiddleware:
    def __init__(self, app):
        self.app = app
        self.profile = json.loads(os.environ["VLLM_SERVER_GENERATION_DEFAULTS"])
        logging.getLogger("vllm").info(
            "Server generation defaults: %s", self.profile.get("model")
        )

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or scope.get("path") not in {"/v1/chat/completions", "/v1/completions"}):
            return await self.app(scope, receive, send)
        chunks = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            pass  # 通常のAPI検証に任せる。
        else:
            body = json.dumps(apply_defaults(payload, self.profile),
                              ensure_ascii=False).encode("utf-8")
        headers = [(key, value) for key, value in scope.get("headers", [])
                   if key.lower() not in {b"content-length", b"transfer-encoding"}]
        headers.append((b"content-length", str(len(body)).encode("ascii")))
        new_scope = {**scope, "headers": headers}
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(new_scope, replay, send)
