# vllm-server

**新しいLLMエージェントは、作業前に [AGENTS.md](AGENTS.md) と [HANDOFF.md](HANDOFF.md) を読むこと。**
HANDOFFにはこれまでの経緯、操作上の注意、モデル切り替え、GitHub展開の前提を記録している。
ユーザーが実験中のサーバーには、説明や確認のために勝手に接続・停止・再起動しない。

大量実験向けの vLLM サーバー。config から起動し、必要なら Cloudflare Tunnel で公開する。
個々の応答時間より、固定した実験セットを処理し終えるまでの総時間を重視する。

対象は **Linux / WSL2・Python 3.12・NVIDIA GPU**。A100 (sm_80) と RTX 3090 (sm_86)
で同じスクリプトを使用し、そのマシンで調整した値を `configs/local.yaml` に保存する。
動作確認結果は [docs/validation.md](docs/validation.md) を参照。

現在、A100 MIG 3g.40gb で **32K設定・21,043トークン入力への応答を確認済み**。
RTX 3090は未検証。実験データを使った最適な並列数の測定はこれから行う。

## 最初に使う

```bash
git clone https://github.com/kaiKyutech/vllm-server.git
cd vllm-server
./setup/install.sh
./scripts/doctor.sh
```

`uv` が PATH にない場合はプロジェクト内の `.tools/` に導入する。システムPython、
ドライバ、CUDA Toolkit、conda環境は変更しない。`pyproject.toml` と `uv.lock` の依存関係を使い、
再実行しても勝手に最新版にしない。Python 3.12 が既に必要。

初回だけ `configs/server.sample.yaml` が `configs/local.yaml` にコピーされる。
その後の設定は上書きしない。vLLM 0.19.1 / PyTorch 2.10.0 CUDA 12.9 の配布パッケージを使用する。
`nvidia-smi` の CUDA 表示はドライバの対応上限で、インストール済みToolkitのバージョンとは異なる。
対応可否は `doctor.sh` と実際の推論で確認する。

RTX 3090で初めて使う場合は [3090向け手順](docs/rtx3090.md) を参照。
24GB向けに小さい並列数・コンテキストから確認する。3090実機での動作は未検証。

### モデル取得（明示的に実行）

```bash
./scripts/download.sh Qwen/Qwen3.5-9B
```

指定した1モデルだけを取得する。初期設定は公式の **Qwen/Qwen3.5-9B BF16**。
GGUF / ONNX 等の別形式や別サイズのモデルは取得しない。
モデル本体は **`models/Qwen3.5-9B/`** に直接保存し、HFキャッシュに重みの別コピーを作らない。
Qwen3.5-9Bの既定revisionは `c202236235762e1c871ad0ccb60c8ee5ba337b9a`。
取得元・revision・容量はモデルフォルダ内の `.download-info.json` に記録する。
別revisionを使う場合は `--revision <commit>` を指定する。

取得スクリプトは `model.safetensors.index.json` の重み一覧を優先し、単一版・分割版・
`original/` 等を重複して保存しない。複数の重みから一意に選べない場合は停止する。
`--dry-run` は索引だけ取得して重みの取得計画を表示する。
取得済みモデルとrevisionは [docs/models.md](docs/models.md) に記録。

### 起動

```bash
./scripts/start.sh configs/local.yaml

# 詳細ログ
LOG_VERBOSITY=4 ./scripts/start.sh configs/local.yaml

# configを編集せず一時的に引数を上書きする場合
./scripts/start.sh configs/local.yaml --max-num-seqs 16
```

`Ctrl+C` で終了する。バックグラウンドへの自動移行はしない。
起動では依存関係の更新・モデルの自動取得をしない。モデル未取得なら取得手順を実行する。
なお GPU カーネルの初回コンパイルは発生し、構成によってはカーネル関連の取得も発生する。

## configを調整する

`configs/local.yaml` は vLLM 標準の YAML。CLI引数の `--` を外したキー名を使う。
必要な vLLM オプションはそのまま追記できる。明示的なCLI引数がYAMLより優先される。

| 設定 | 意味・調整方針 |
|---|---|
| `model` | ローカルのモデルパス。初期値 `models/Qwen3.5-9B`。相対パスはプロジェクトルート基準 |
| `served-model-name` | APIで指定するモデル名。初期値 `qwen35-9b` |
| `max-model-len` | 入力 + thinking + 出力の合計上限。初期案32,768。`auto`も可 |
| `gpu-memory-utilization` | 使用するVRAMの割合。初期案0.95。OOM時は下げる |
| `max-num-seqs` | 同時処理数の上限。初期案32。最適値は実験データで測る |
| `max-num-batched-tokens` | 1ステップで処理するトークン数の上限。コンテキスト長とは別。初期案16,384 |
| `language-model-only` | 初期値true。画像等を使う場合に変更して別途検証する |
| `generation-config` | 初期値auto。モデル付属の生成設定を採用。リクエストで上書き可能 |
| `enable-prefix-caching` | 初期値false。共通prefixが多い実験ではtrueも比較する |

vLLMは実メモリをプロファイルしてキャッシュを用意する。`max-model-len: auto` は
収まる最大長を選ぶが、最適な並列数や「全リクエストが同時にその長さを使えること」は保証しない。
キャッシュ不足による中断・再計算 (preemption) が多い場合は並列上限やバッチトークン数を下げる。
32Kの入力20Kなら、残り約12Kがthinking・出力・テンプレート等の余地となる。

### サーバー側の生成既定値

`start.sh` はモデル名に対応する `configs/generation/<モデル名>.json` を自動選択し、
**クライアントが省略した生成パラメータだけ**を補う。追加のAPIサーバーは立てず、
vLLM標準の `--middleware` 拡張を利用する。対象は `/v1/chat/completions` と `/v1/completions`。

| モデル | temperature | top_p | top_k | presence_penalty | 根拠 |
|---|---:|---:|---:|---:|---|
| Qwen3.5-9B・thinking | 1.0 | 0.95 | 20 | 1.5 | 公式の一般タスク推奨 |
| Qwen3.5-9B・非thinking | 0.7 | 0.8 | 20 | 1.5 | 公式の一般タスク推奨 |
| gpt-oss-20b | 1.0 | 1.0 | 0（無制限） | 0 | 数値の公式推奨が付属設定にないためvLLMの中立的既定値 |
| Ministral 3 8B | 0.05 | 1.0 | 0 | 0 | 公式推奨のtemperature<0.1を満たす選択。他は中立的既定値 |
| Phi-4-mini-instruct | 0.0 | 1.0 | 0 | 0 | 公式モデルカードのvLLM実行例（greedy） |
| Gemma 4 E4B | 1.0 | 0.95 | 64 | 0 | モデル付属generation_config |

これらは出発点であり、全タスク共通の「最適値」ではない。根拠URLと判断は各JSONに記録。
thinkingの指定を省略した場合、そのモデルの公式テンプレートの既定動作を維持する。
Qwenで `enable_thinking: false` を明示した場合だけ、非thinkingの推奨値へ切り替える。
gpt-ossのreasoning_effortも省略時はモデルの既定動作に任せる。

優先順位は **クライアントの明示値 → configのoverride-generation-config → この推奨JSON**。
JSONにない項目（停止トークン等）は引き続きモデル付属設定とvLLMが扱う。
`temperature: 0` のような明示的な0は上書きしない。nullは省略として扱う。
`max_tokens` / `max_completion_tokens` は固定値を注入しない。実験の出力予算はクライアントから指定する。

起動時に選ばれたJSONを表示し、内容を `runtime/active-generation-defaults.json` に記録する。
JSONを変更したらサーバーを再起動する。別名のモデルフォルダを使う場合は
`.env` の `GENERATION_DEFAULTS_FILE` でJSONの絶対パスを指定できる。
未知のモデルに対応するJSONがなければ、その旨を表示してモデル付属設定とvLLMの既定値を使う。

研究で再現性を保つには、設定JSONとモデルrevisionを記録する。リクエストで上書きした値も記録する。
`chat_template_kwargs: {"enable_thinking": false}` でQwen3.5のthinkingを無効化できる。
モデルを変える場合はparserやthinking設定も新モデルに合わせる。

将来、別モデルを取得する場合は `./scripts/download.sh 組織名/モデル名` を明示的に実行し、
`model: models/モデル名` に変更する。保存先を指定したい場合は `--directory <パス>` を使う。
別組織の同名モデルは保存先を分ける。HFモデルIDを直接configへ設定しても、起動はオフラインなので
未キャッシュのモデルを勝手に取得することはない。

今回取得した追加モデルには `configs/gpt-oss-20b.sample.yaml`、`ministral-3-8b.yaml`、
`phi-4-mini.sample.yaml`、`gemma-4-e4b.sample.yaml` を用意した。
これらはGPU別ではなくモデル別の起動例。QwenとMinistralは実推論確認済み。
Ministralは `./scripts/start.sh configs/ministral-3-8b.yaml` で起動する。
他3モデルの実推論は未検証。
例えば `./scripts/start.sh configs/gpt-oss-20b.sample.yaml` で切り替える。
同じGPU・同じポートで複数モデルを同時起動することは想定しない。

## API接続と外部公開

まずローカルで確認する。

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen35-9b","messages":[{"role":"user","content":"日本語で挨拶してください。"}],"max_tokens":128,"stream":false,"chat_template_kwargs":{"enable_thinking":false}}'
```

### cloudflaredの導入

既にインストールしてあれば不要。スクリプトは PATH、`.tools/cloudflared`、既存の `~/bin/cloudflared` を探す。
このDocker環境で新たに導入する場合は、再起動後も残るプロジェクト配下へ置く。

```bash
mkdir -p .tools
curl -L -o .tools/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x .tools/cloudflared
```

### 公開

vLLMとは別のターミナルで実行する。vLLMを再起動してもTunnelは独立して維持される。

```bash
./scripts/tunnel.sh 8000
```

表示された `https://....trycloudflare.com/v1` をクライアントのbase URLに指定する。
Quick Tunnelでは `stream: false` を使用する。SSEは公式には非対応。
同時に処理中のHTTPリクエストは200件まで。長い生成でタイムアウトする場合は、
ローカルでの処理結果と比較し、生成長・同時投入数・公開経路を調整する。

APIキーを使う場合は `.env.example` を `.env` にコピーし `VLLM_API_KEY` を設定してvLLMを再起動する。
クライアントは `Authorization: Bearer <キー>` を送る。APIキーはGitへ含めない。
追加のFastAPIや独自ゲートウェイは使わない。

## 大量実験の処理量を測る

```bash
# 合成データによる簡単な確認。同じ64件を並列数を変えて処理する。
./scripts/bench.sh --warmup --requests 64 --concurrency 1 2 4 8 16 32

# 実験データを使う（こちらを重視）
./scripts/bench.sh --jsonl runtime/requests.jsonl \
  --warmup --concurrency 4 8 16 32 --output runtime/bench-real.json
```

JSONLは1行1リクエスト。例えば:

```json
{"messages":[{"role":"user","content":"ここに実験の入力"}],"max_tokens":2048,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}
```

`stream: false` で処理し、成功件数/秒、総トークン/秒、出力トークン/秒、エラー数、
出力上限に達した件数を記録する。APIキーは結果に保存しない。
既定ではthinkingなし。`--thinking` またはJSONLで有効化する。
`--save-responses` を付けると応答本文も保存する。JSONL指定時は全行を各並列数で処理する。

クライアントの同時投入数とサーバーの `max-num-seqs` は別。
サーバー設定を変えたら再起動し、同じデータ・生成設定で比較する。
並列数を増やしたときの失敗、再計算、応答切り詰めも確認し、固定した実験セットの総時間が
最短になる値を `local.yaml` に保存する。短い合成データの最適値を20K入力へそのまま適用しない。

外部経由でも測定可能:

```bash
./scripts/bench.sh --url https://YOUR-URL.trycloudflare.com/v1 \
  --jsonl runtime/requests.jsonl --concurrency 4 8 16
```

## 保存先・容量管理

| 場所 | 内容 | Git管理 |
|---|---|---|
| `.venv/` | このプロジェクトのPython環境 | 対象外 |
| `.tools/` | ローカル導入したuv | 対象外 |
| `models/` | モデル本体とtokenizer | 対象外 |
| `runtime/huggingface/` | HFの管理情報等（モデル本体はmodelsに直接保存） | 対象外 |
| `runtime/vllm-cache/` / `runtime/triton-cache/` | コンパイル結果 | 対象外 |
| `runtime/` | ログ・測定結果・ローカルデータ | 対象外 |
| `configs/local.yaml` / `.env` | マシン設定・秘密情報 | 対象外 |
| `pyproject.toml` / `uv.lock` / サンプル設定・スクリプト | 別環境への再現に必要なファイル | 対象 |

このDocker環境では **srv11配下だけが再起動後も残る** 前提で、仮想環境・モデル・
各種キャッシュ・作業用一時ファイルをすべてこのプロジェクト配下に置く。
`runtime/tmp/` も用意し、`/tmp` やホームディレクトリのキャッシュを永続データの保存先にしない。
別マシンで保存先を変える場合は `.env` へ絶対パスを指定する。
`UV_PROJECT_ENVIRONMENT` はセットアップ・起動で同じ値にする。

```bash
du -h --max-depth=1 .
```

## 問題が起きたとき

- **GPU未認識・import失敗**: `./scripts/doctor.sh` の出力、ドライバ版、GPU名を確認。
  CUDA Toolkitの入れ直しやtorchだけの更新を先に行わない。
- **VRAM不足**: 他のGPUプロセスを確認。必要コンテキストを維持しながら `max-num-seqs`、
  `max-num-batched-tokens` を下げる。CUDA graph等にもメモリが必要。
- **未取得モデル**: `download.sh` を実行する。startはオフラインのため自動取得しない。
- **3090で同じ設定が収まらない**: 実機でconfigを調整する。BF16が厳しければ対応量子化を別途検証する。
- **Tunnelだけ失敗**: ローカルの `/health` とAPI応答を確認。`TUNNEL_PROTOCOL=quic` も指定可能。
- **初回が遅い**: モデル読み込みとカーネルコンパイルを待つ。完了後にウォームアップして測定する。

## 参考

- [vLLM GPU installation](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/)
- [vLLM tuning](https://docs.vllm.ai/en/stable/configuration/optimization/)
- [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Cloudflare Quick Tunnelの制限](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
