"""指定した1モデルだけを models/ へ取得する。重みのキャッシュ複製は作らない。"""
import argparse
import fnmatch
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download


def select_files(filenames, index=None):
    """Transformers形式の重みを1組だけ選び、original/やconsolidatedの重複を除く。"""
    names = set(filenames)
    root = {name for name in names if "/" not in name}
    if index is not None:
        weights = set(index["weight_map"].values())
        if not weights or not weights <= names:
            raise ValueError("重みの索引が空か、配布ファイル一覧と一致しません")
    elif "model.safetensors" in root:
        weights = {"model.safetensors"}
    else:
        candidates = {name for name in root if name.endswith(".safetensors")}
        if len(candidates) != 1:
            raise ValueError("重みを一意に選べません。対応するsafetensors索引を確認してください")
        weights = candidates
    auxiliary = {name for name in root if any(fnmatch.fnmatch(name, pattern) for pattern in
                 ["*.json", "*.jinja", "*.tiktoken", "*.txt", "*.model", "*.md", "LICENSE*"])}
    return sorted(weights | auxiliary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--revision")
    parser.add_argument("--directory", help="保存先。既定はプロジェクトのmodels/<モデル名>")
    parser.add_argument("--dry-run", action="store_true", help="索引のみ取得し、重みの取得計画を表示")
    args = parser.parse_args()
    model = args.model
    revision = args.revision or (
        "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
        if model == "Qwen/Qwen3.5-9B" else "main"
    )
    root = Path(__file__).resolve().parents[1]
    destination = Path(args.directory).resolve() if args.directory else root / "models" / model.rsplit("/", 1)[-1]
    info = HfApi().model_info(model, revision=revision, files_metadata=True)
    by_name = {f.rfilename: f for f in info.siblings}
    index_name = "model.safetensors.index.json"
    index = None
    if index_name in by_name:
        local_index = hf_hub_download(repo_id=model, revision=info.sha,
                                      filename=index_name, local_dir=destination)
        index = json.loads(Path(local_index).read_text())
    selected = select_files(by_name, index)
    files = [by_name[name] for name in selected]
    total = sum(f.size or 0 for f in files)
    print(f"取得対象: {model}\nrevision: {info.sha}\n最大取得量: {total / 1e9:.2f} GB", flush=True)
    print("取得する重み: " + ", ".join(name for name in selected if name.endswith(".safetensors")), flush=True)
    if args.dry_run:
        return
    dest = snapshot_download(repo_id=model, revision=info.sha, local_dir=destination,
                             allow_patterns=selected, max_workers=4)
    report = destination / ".download-info.json"
    report.write_text(json.dumps({"model": model, "revision": info.sha,
                                  "snapshot": dest, "bytes": total, "files": selected}, indent=2) + "\n")
    print(f"取得完了: {dest}")
    print("起動時の再取得はありません。")


if __name__ == "__main__":
    main()
