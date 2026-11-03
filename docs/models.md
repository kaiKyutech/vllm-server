# ローカルに取得したモデル

2026-11-02時点。モデル本体はすべて `models/` 配下。
2026-11-03追記: Qwen3.5-9BとMinistral 3 8B BF16はGPU推論確認済み。
他3モデルは取得ファイルの存在・サイズ・索引を検証済みで、GPU推論は未検証。

| モデル | 形式 | 取得容量（10進GB） | revision |
|---|---|---:|---|
| Qwen/Qwen3.5-9B | BF16 | 約19.329 | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| openai/gpt-oss-20b | MXFP4 | 約13.789 | `6cee5e81ee83917806bbde320786a8fb61efebee` |
| mistralai/Ministral-3-8B-Instruct-2512-BF16 | BF16 | 約17.870 | `f6fae9795746f63c9be8344932f01275f3c63734` |
| microsoft/Phi-4-mini-instruct | BF16 | 約7.694 | `cfbefacb99257ffa30c83adab238a50856ac3083` |
| google/gemma-4-E4B-it | BF16 | 約16.025 | `ee0ef6023621cff504d758262d4e04895a5af4a2` |

追加4モデルの合計は約55.378GB。Gemma 4 26B-A4Bはこの環境へ取得していない。
gpt-ossの `original/`・`metal/`、Ministralの `consolidated.safetensors` は重複形式のため除外した。
MinistralはHugging Face形式の4分割safetensorsだけを保存する。

## 切り替え

現在のサーバーを終了してから、次のいずれかを実行する。同一GPU・ポートでの同時起動はしない。

```bash
./scripts/start.sh configs/local.yaml
./scripts/start.sh configs/gpt-oss-20b.sample.yaml
./scripts/start.sh configs/ministral-3-8b.yaml
./scripts/start.sh configs/phi-4-mini.sample.yaml
./scripts/start.sh configs/gemma-4-e4b.sample.yaml
```

起動例のメモリ設定は出発点。20K入力での最適な並列数を保証しない。
新しいモデルを試す際は、ローカルAPI応答とメモリ使用量を先に検証する。

## 生成既定値の出典

- [Qwen3.5-9B公式README](https://huggingface.co/Qwen/Qwen3.5-9B#best-practices): 一般タスクのthinking / 非thinking別推奨。
- [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b): 付属生成設定にtemperature/top_pの値はない。現状はvLLM標準値を明示し、公式最適値とは扱わない。
- [Ministral公式推奨](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512#recommended-settings): temperature<0.1から0.05を選択。
- [Phi-4-mini公式vLLM例](https://huggingface.co/microsoft/Phi-4-mini-instruct#inference-with-vllm): temperature=0。
- [Gemma 4 E4B付属生成設定](https://huggingface.co/google/gemma-4-E4B-it/blob/main/generation_config.json): temperature=1、top_p=0.95、top_k=64。

詳細は `configs/generation/*.json` を参照。クライアントが値を明示した場合はそちらが優先される。
