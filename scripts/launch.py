"""configのモデルに対応する推奨設定を選び、同じvLLMサーバーへ渡す。"""
import argparse
import json
import os
from pathlib import Path
import sys

import yaml


def main():
    config_path = Path(sys.argv[1]).resolve()
    extra = sys.argv[2:]
    config = yaml.safe_load(config_path.read_text())
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--model")
    parser.add_argument("--override-generation-config", type=json.loads)
    known, _ = parser.parse_known_args(extra)
    model = known.model or config["model"]
    root = Path(__file__).resolve().parents[1]
    profile_path = Path(os.environ.get("GENERATION_DEFAULTS_FILE") or
                        root / "configs" / "generation" / (Path(model).name + ".json"))
    middleware = []
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text())
        overrides = (known.override_generation_config if known.override_generation_config is not None
                     else config.get("override-generation-config", {}))
        if isinstance(overrides, str):
            overrides = json.loads(overrides)
        # max_new_tokensはvLLM自身の処理に任せ、出力上限の二重指定を避ける。
        profile["server_overrides"] = {k: v for k, v in overrides.items()
                                       if k not in {"max_new_tokens", "max_tokens", "max_completion_tokens"}}
        os.environ["VLLM_SERVER_GENERATION_DEFAULTS"] = json.dumps(profile)
        scripts = str(root / "scripts")
        os.environ["PYTHONPATH"] = scripts + os.pathsep + os.environ.get("PYTHONPATH", "")
        middleware = ["--middleware", "generation_defaults.GenerationDefaultsMiddleware"]
        report = root / "runtime" / "active-generation-defaults.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
        print(f"サーバー生成既定値: {profile_path}", flush=True)
        print(json.dumps(profile, ensure_ascii=False), flush=True)
    else:
        print("生成既定値プロファイルなし。モデル付属設定とvLLMの既定値を使用します。", flush=True)
    executable = Path(sys.executable).parent / "vllm"
    os.execv(str(executable), [str(executable), "serve", "--config", str(config_path),
                             *middleware, *extra])


if __name__ == "__main__":
    main()
