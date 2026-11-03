#!/usr/bin/env python3
"""固定件数を各並列数で処理する。stream=false。JSONL実データも利用可能。"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import time
import uuid

import httpx


async def run_batch(client, args, model, concurrency, items, warmup=False):
    queue = asyncio.Queue()
    for i, item in enumerate(items):
        queue.put_nowait((i, item))
    results = []

    async def worker():
        while True:
            try:
                index, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if isinstance(item, str):
                # prefix cache による合成ベンチの偏りを抑えるため先頭に固有IDを置く。
                messages = [{"role": "user", "content": f"ID: {uuid.uuid4().hex}\n{item}"}]
                payload = {"messages": messages}
            else:
                payload = dict(item)
            payload.setdefault("max_tokens", args.max_tokens)
            payload.setdefault("temperature", 0)
            payload.setdefault("chat_template_kwargs", {"enable_thinking": args.thinking})
            payload.update(model=model, stream=False)
            started = time.perf_counter()
            record = {"index": index}
            try:
                response = await client.post(args.url.rstrip("/") + "/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                if not data.get("choices") or "usage" not in data:
                    raise ValueError("choices または usage がないレスポンス")
                record.update(ok=True, usage=data["usage"],
                              finish_reason=data["choices"][0].get("finish_reason"))
                if args.save_responses:
                    record["response"] = data
            except Exception as exc:
                record.update(ok=False, error=str(exc))
                if isinstance(exc, httpx.HTTPStatusError):
                    record["error_body"] = exc.response.text[:2000]
            record["seconds"] = time.perf_counter() - started
            results.append(record)
            queue.task_done()

    started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(min(concurrency, len(items)))))
    elapsed = time.perf_counter() - started
    ok = [r for r in results if r["ok"]]
    prompt = sum(r["usage"].get("prompt_tokens", 0) for r in ok)
    output = sum(r["usage"].get("completion_tokens", 0) for r in ok)
    summary = {
        "concurrency": concurrency, "requests": len(items), "success": len(ok),
        "errors": len(results) - len(ok), "elapsed_seconds": elapsed,
        "successful_requests_per_second": len(ok) / elapsed,
        "prompt_tokens": prompt, "completion_tokens": output,
        "total_tokens_per_second": (prompt + output) / elapsed,
        "output_tokens_per_second": output / elapsed,
        "mean_request_seconds": statistics.mean(r["seconds"] for r in results),
        "truncated_responses": sum(r.get("finish_reason") == "length" for r in ok),
    }
    if not warmup:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary, results


async def main(args):
    if args.jsonl:
        items = [json.loads(line) for line in Path(args.jsonl).read_text().splitlines() if line.strip()]
        if not items:
            raise ValueError("JSONL が空です")
    else:
        items = [args.prompt] * args.requests
    if not items or args.requests < 1 or any(c < 1 for c in args.concurrency):
        raise ValueError("件数と並列数には正の値を指定してください")
    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    limits = httpx.Limits(max_connections=max(args.concurrency),
                          max_keepalive_connections=max(args.concurrency))
    async with httpx.AsyncClient(headers=headers, timeout=args.timeout, limits=limits,
                                 trust_env=False) as client:
        model = args.model
        if not model:
            r = await client.get(args.url.rstrip("/") + "/models")
            r.raise_for_status()
            model = r.json()["data"][0]["id"]
        if args.warmup:
            summary, _ = await run_batch(client, args, model, 1, items[:1], warmup=True)
            if summary["errors"]:
                raise RuntimeError("ウォームアップに失敗しました")
        reports = []
        for concurrency in args.concurrency:
            summary, records = await run_batch(client, args, model, concurrency, items)
            reports.append({"summary": summary, "requests": records})
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"model": model, "url": args.url,
                               "arguments": {k: v for k, v in vars(args).items() if k != "api_key"},
                               "runs": reports}, ensure_ascii=False, indent=2) + "\n")
    print(f"保存: {dest}")
    if any(r["summary"]["errors"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--model")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY"))
    p.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4, 8, 16, 32])
    p.add_argument("--requests", type=int, default=64)
    p.add_argument("--prompt", default="日本の四季の特徴を詳しく説明してください。")
    p.add_argument("--jsonl", help="1行1リクエストのJSON（messages、max_tokensなど）または文字列")
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--thinking", action="store_true", help="既定はthinkingなし。JSONLの明示設定が優先")
    p.add_argument("--warmup", action="store_true")
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--save-responses", action="store_true")
    p.add_argument("--output", default="runtime/bench.json")
    asyncio.run(main(p.parse_args()))
