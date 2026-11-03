# 新しいLLMエージェントへの引き継ぎ

最終更新: **2026-11-02（UTC）**。会話履歴がなくても作業できるように残した記録。
これは過去の状態を含む文書であり、PID・URL・実行状態の現在値を保証するものではない。
新しい作業で状況が変わったら、この文書・README・モデル一覧も必要に応じて更新する。

## 最初に守ること

1. **ユーザーはこの引き継ぎ時点で、Qwenサーバーを自分で起動して実験中。触らない。**
   停止・再起動・モデル切り替え・設定反映・GPUを使う確認・負荷試験は、その時点のユーザー指示が必要。
   `/health` を含む接続確認も、ユーザーが「サーバーに触れないで」と言っている間は実行しない。
   過去にエージェントの検証用サーバーを起動したことがあるが、ユーザーの依頼で停止済み。
   その後、ユーザー自身の運用へ戻している。過去のPIDを使ってシグナルを送らない。
2. **変更するのは `/home/jovyan/work/srv11/` 配下。** このDocker環境では、その外は
   再起動で消える前提。他ユーザーの環境やストレージには触れない。
3. モデルは **このプロジェクトの `models/`** に置く。`.venv/`、`.tools/`、各キャッシュも
   プロジェクト内に置く。外部の一時領域を永続環境として使わない。
4. ユーザーは **自分でコマンドを実行して起動・公開する** ことを希望している。
   「起動の仕方を教えて」という質問を、エージェントによる起動の指示と解釈しない。
5. GitHubへのcommit・push・公開は、明示的な指示があるときだけ。秘密情報やモデルを送らない。

`doctor.sh` はGPUで行列計算をする。`bench.sh` は推論負荷をかける。
`setup/install.sh` は環境を変更する。いずれも「読むだけの確認」ではない。

## ユーザーが目指している運用

- マルチエージェント研究の大量実験。人間向けの応答待ち時間より、**実験セット全体の処理時間**を重視。
- 入力は1件20Kトークン程度以上を想定。最適並列数は実データで今後測る。
- `llama-server` と似た、configを選んで起動し、別ターミナルでCloudflare公開する操作を好む。
- GPU別の複雑なconfig体系や、余分なAPIサーバーを増やしたくない。
  そのマシンで測った値をローカルconfigへ保存する。
- クライアントは簡単にしたい。temperature等を省略するとサーバーがモデル別の設定を補う。
  実験の都合で明示した値はクライアント優先。thinkingの省略時は**公式の既定動作**を維持する。
- 将来、別環境のRTX 3090へ展開し、GitHub経由で管理したい。
  **3090での動作確認はまだ行っていない。**

## 場所と環境

```text
/home/jovyan/work/srv11/
├── llama-server/       # 既存プロジェクト。今回のvLLM変更と混同しない
└── vllm-server/        # このプロジェクト
```

検証時のGPUは、フルGPUのA100 40GBではなく **A100 80GB PCIeのMIG 3g.40gb**。
利用可能メモリ40,192 MiB、42 SMだった。性能をフルA100と同一視しない。

固定した環境: Python 3.12.9、vLLM 0.19.1、PyTorch 2.10.0+cu129、
Transformers 5.5.3、FlashInfer 0.6.6。ドライバ570.86.15でQwenの実推論まで通過。
正確な依存関係は `pyproject.toml` と `uv.lock` が正。
「最新版がよさそう」という理由だけでtorch・vLLM・CUDAを更新しない。

Python 3.12とGPUドライバはDockerのベース環境に提供される前提。
`.venv` のPythonは `/opt/conda/bin/python3` へのリンクを使うため、ベース環境が変わった場合には
固定lockから環境を再構築する。Docker再起動そのものの試験はしていない。

過去の古い `srv11/vllm`、`vllm-112`、`vllm-uv`、`worldmodel` は、容量整理のためユーザー許可で削除した。
これらの古い環境を前提に説明しない。他の既存プロジェクトは整理対象にしていない。

## 起動・外部公開を聞かれたら

**まずはコマンドを案内する。エージェント自身では実行しない。**

```bash
cd /home/jovyan/work/srv11/vllm-server
LOG_VERBOSITY=4 ./scripts/start.sh configs/local.yaml
```

記録時の `local.yaml` はQwen3.5-9B。`LOG_VERBOSITY=4` はDEBUG、通常は3でINFO。
前景起動で、ユーザーのターミナルから `Ctrl+C` で停止する。
起動が遅くても即座に失敗と判断しない。初回はコンパイル・プロファイルで数分かかった。

別ターミナルで:

```bash
cd /home/jovyan/work/srv11/vllm-server
./scripts/tunnel.sh 8000
```

Cloudflareの実行ファイルは `.tools/cloudflared` に保存済み。
スクリプトはPATH・プロジェクト内・既存の `~/bin/cloudflared` を探索する。
新たに導入する場合の手順もREADMEにあり、保存先は `.tools/`。
サーバーとトンネルは別プロセスなので、片方の停止・再起動で他方まで勝手に停止しない。

外部クライアントの設定:

```text
base_url = https://起動時に表示されたURL.trycloudflare.com/v1
model = qwen35-9b
```

OpenAI互換の `/v1/chat/completions` を使う。Quick Tunnelでは `stream: false` を基本とする。
Quick TunnelのSSE非対応は、非ストリーミングの実験利用まで禁止する意味ではない。
長いリクエストのタイムアウトや同時HTTPリクエスト数の制限は別途考慮する。
昔のURLは期限切れになり得るため、会話にあったURLを現在の接続先と決めつけない。
過去の1回の確認では古いURLがHTTP 530、ローカルAPIは200だった。
**今の公開状態を確認した記録ではない。**

`.env` に `VLLM_API_KEY` があればBearer認証を使う。秘密値をログや回答へ出さない。
`.env.example` は説明用で、実際の `.env` はGit対象外。

## 現在のQwen設定と並列数の意味

設定本体は `configs/local.yaml`。記録時点の主な値:

```yaml
model: models/Qwen3.5-9B
served-model-name: qwen35-9b
host: 127.0.0.1
port: 8000
dtype: bfloat16
gpu-memory-utilization: 0.95
max-model-len: 32768
max-num-seqs: 32
max-num-batched-tokens: 16384
enable-chunked-prefill: true
language-model-only: true
reasoning-parser: qwen3
generation-config: auto
enable-prefix-caching: false
```

- `max-model-len`: 1件の入力＋thinking＋出力の合計上限。文字数ではなくトークン数。
  `auto` も使えるが、最適並列数を自動探索する意味ではない。
- `max-num-seqs`: 実行時に同時処理する件数の上限。32にしても、1件しか送らなければ処理するのは1件。
  計算能力を常に32分割する指定ではない。ただし、起動時のバッファ等の違いまで同一とは保証しない。
- コンテキスト32K・上限32は、32件すべてが同時に32K使えるメモリ保証ではない。
- `max-num-batched-tokens`: 1ステップの処理トークン予算。1件の長さの上限とは別。
- サーバー上限32を維持したまま、送信側を4・8・16・32へ変えて測定できる。
  上限が高いほど必ず速いわけではなく、キャッシュ不足による再計算で効率が下がる場合もある。

configの変更にはサーバー再起動が必要。**実験中に勝手に編集・反映しない。**

## サーバー側のtemperature等は独自の補完処理がある

ここは変更時に特に注意する。

```text
scripts/start.sh
  → scripts/common.sh（保存先・環境変数）
  → scripts/launch.py（モデル名からJSONを選択）
  → vllm serve + 標準の--middleware拡張
  → scripts/generation_defaults.py（省略項目だけ補完）
```

`configs/generation/<モデルフォルダ名>.json` が設定本体。
Qwenには配布元の `generation_config.json` がなかったため、**`generation-config: auto` だけでは
公式READMEの推奨値は入らなかった**。さらにvLLM 0.19.1の通常のgeneration config読込では
`presence_penalty` を既定値にできなかった。このため、別APIサーバーを立てずに
vLLM内の小さなASGIミドルウェアで補っている。

`vllm serve` を直接実行すると、この補完処理を通らない。通常は必ず `start.sh` を使う。

- 優先順位: **クライアントの明示値 → configのoverride-generation-config → 推奨JSON**。
- 明示的な0は保持。nullは省略として扱う。
- 対象はChat CompletionsとCompletions。すべてのAPIに適用されるとは説明しない。
- 停止トークン等はモデル付属設定に任せる。出力トークン上限は補完JSONから固定しない。
- thinking自体は注入せず、公式テンプレートの省略時動作を維持する。
- Qwenは省略時にthinkingの一般推奨値を補い、明示OFF時は非thinkingの一般推奨値へ切り替える。
- `runtime/active-generation-defaults.json` は起動時の記録。停止後も残るので、稼働の証拠にはならない。
- モデルフォルダを別名にしたら自動選択できない場合がある。
  必要なら `.env` の `GENERATION_DEFAULTS_FILE` でJSONの絶対パスを指定する。
- 推奨JSONがない未知モデルは、警告してモデル付属設定・vLLM既定値を使う。

| モデル／モード | temperature | top_p | top_k | presence_penalty |
|---|---:|---:|---:|---:|
| Qwen・thinking | 1.0 | 0.95 | 20 | 1.5 |
| Qwen・非thinking | 0.7 | 0.8 | 20 | 1.5 |
| gpt-oss-20b | 1.0 | 1.0 | 0 | 0 |
| Ministral 3 8B | 0.05 | 1.0 | 0 | 0 |
| Phi-4-mini | 0.0 | 1.0 | 0 | 0 |
| Gemma 4 E4B | 1.0 | 0.95 | 64 | 0 |

根拠は各JSONと [docs/models.md](docs/models.md)。gpt-ossは数値の公式推奨が付属設定になく、
vLLMの中立的既定値を採用。Ministralの0.05は公式推奨の「0.1未満」から選んだ値。
Phiの0は公式実行例に合わせた値。全モデル・全実験の最適値を保証する仕組みではない。

Qwenのリクエスト例:

```json
{"chat_template_kwargs": {"enable_thinking": false}}
```

gpt-ossは `reasoning_effort` の `low` / `medium` / `high` を使う。
`low` を推論OFFと同一視しない。他モデルでも同じ指定が使えるとは決めつけない。
別GPUのllama.cpp側の設定は、このミドルウェアの対象外。

## モデル切り替えと取得済みモデル

詳細なモデルID・revision・サイズは [docs/models.md](docs/models.md)。

| models内のフォルダ | APIモデル名 | 起動config | 検証 |
|---|---|---|---|
| `Qwen3.5-9B` | `qwen35-9b` | `configs/local.yaml` | GPU推論確認済み |
| `gpt-oss-20b` | `gpt-oss-20b` | `configs/gpt-oss-20b.sample.yaml` | 取得のみ |
| `Ministral-3-8B-Instruct-2512-BF16` | `ministral-3-8b` | `configs/ministral-3-8b.sample.yaml` | 取得のみ |
| `Phi-4-mini-instruct` | `phi-4-mini` | `configs/phi-4-mini.sample.yaml` | 取得のみ |
| `gemma-4-E4B-it` | `gemma-4-e4b` | `configs/gemma-4-e4b.sample.yaml` | 取得のみ |

Gemma 4 26B-A4Bは、ユーザーが**別GPUのllama.cpp**で実験している。この環境へは取得していない。
モデル比較は通常の研究評価用途で、学習データセット生成を目的としていない。

モデル切り替えは、ユーザーが現在のサーバーを終了してから、例えば:

```bash
./scripts/start.sh configs/gpt-oss-20b.sample.yaml
```

同じGPU・ポートで2つのサーバーを同時起動しない。Qwenの `reasoning-parser: qwen3` を
他モデルへ無条件に流用しない。追加4モデルのサンプルconfigは**実推論未検証**。
gpt-ossのA100向けMarlin経路は公開実装上で確認したが、ここでの実推論速度はまだ測っていない。

既にモデルがあるなら再取得は不要。新規取得の基本形:

```bash
./scripts/download.sh 組織名/モデル名 --revision コミットID
```

`download.py` はsafetensors索引のファイルだけを選ぶ。
gpt-ossの `original/` / `metal/`、Ministralの `consolidated.safetensors` を重複取得しない。
`.download-info.json` に取得元・revision・対象ファイル・容量を記録する。
取得済み4モデルは存在・サイズ・不要重みがないことまで確認済み。
新しい取得や別形式の追加は容量に影響するので、ユーザーが依頼した範囲を守る。

## 実測とベンチマークの注意

詳細は [docs/validation.md](docs/validation.md)。Qwen BF16・このMIG環境で確認した値:

- コンテキスト32Kで、入力21,043トークン＋出力4トークンを約5.62秒で処理。
  合成した繰り返し入力の末尾の合言葉に答える確認であり、一般の長文理解性能を保証しない。
- 短い約50トークン入力、各64出力トークン、16リクエストの簡易測定:
  並列1: 43.8、4: 159.3、8: 302.7、16: 531.0 **出力トークン/秒（全体）**。
- サーバー上限は全測定で32。531 tok/sを1リクエストあたりの速度と説明しない。
- 20K入力での最適並列数は未測定。llama.cppとの同条件の比較もしていない。
- 生成既定値のCPUテスト7件と、Qwen実サーバーで省略値と明示値の応答一致を確認済み。

性能測定の案内例（実験中には実行しない）:

```bash
./scripts/bench.sh --jsonl runtime/requests.jsonl --warmup \
  --concurrency 4 8 16 32 --output runtime/bench-real.json
```

指定した各並列数でJSONL全行を処理するので、実験回数はその分増える。
他の実験と同時に測ると結果が混ざる。総時間、成功件数、エラー、出力切り詰め、
キャッシュ不足による再計算を考慮する。
**bench.pyは既定でtemperature=0とthinkingなしをクライアントから指定する。**
サーバー推奨値の評価をしたい場合、このクライアント側の指定も確認すること。
実験用JSONLを用意する際は、実際の生成条件を明示し、設定JSONとともに保存する。

## 容量・永続化

- 最後の計測では、このプロジェクト全体が約81 GiB（`du -h` の81G）。
  モデル約70 GiB、仮想環境約11 GiB。現在値ではなく2026-11-02の記録。
- Qwenのモデルファイル約19.329GB、追加4モデル合計約55.378GB（こちらは10進GB）。
- ディスク全体の空きは過去の確認で約3.8 TiBだったが、**個人専用の利用上限ではない**。
  個人クォータは確認できなかった。ユーザーの使用許容量と混同しない。
- `scripts/common.sh` がHF、uv、Torch、Triton、CUDA、FlashInfer等のキャッシュ先と
  `TMPDIR` をプロジェクトの `runtime/` にまとめる。
- サーバー起動ではモデル取得をしない。`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`。
  初回のカーネル構築やカーネル関連の取得は別に発生し得る。

## GitHub・別GPUへの展開を依頼されたら

記録時点では、このフォルダに `.git/` はなく、GitHubリポジトリ作成・remote設定・
commit・pushは行っていない。ユーザーの希望は将来的な連携であり、既に公開済みとは言わない。

- README、AGENTS、HANDOFF、スクリプト、サンプルYAML、生成設定JSON、テスト、
  `pyproject.toml`、`uv.lock`、docsを管理対象にする。
- `.gitignore` は `.venv/`、`.tools/`、`models/`、`runtime/`、`.env`、
  `configs/local.yaml`、Pythonキャッシュを除外している。
- `configs/local.yaml` はGit対象外なので、別マシンではサンプルから作る。
  モデル別サンプルと生成既定値JSONは引き継げる。
- APIキー、トンネルトークン、実験の非公開データ、ログをコミットしない。
- `setup/install.sh` はuvを使い、lockから環境を作る。モデルは別途取得する。
  初回の環境配置はこのストレージで15分半程度かかった。再実行は既存環境を監査する。
- RTX 3090では24GBとなり、同じメモリ設定が収まるとは保証しない。
  その実機のドライバ・GPU・必要コンテキストを確認し、実測して調整する。
- GitHubの所有者・リポジトリ名・公開範囲は、新しい依頼の内容に従って決める。

## 残っている作業と誤認しやすい点

- 追加4モデルの実推論・互換性確認は未実施。
- 20K入力・実験データによる最適並列数の探索は未実施。
- 3090実機とDocker再起動後の検証は未実施。
- 現在のCloudflare URL・稼働状態は、この引き継ぎでは確認していない。
- runtimeの起動ログやactive-generation-defaults.jsonは、過去の記録である場合がある。
- この文書を読むことは、サーバーを停止・起動・試験利用してよいという許可ではない。

新規セッションではまずこの文書と関連ファイルを読み、ユーザーの今回の目的に必要な
作業だけを進める。特に、実験中のサーバーの操作権限を過去の会話から推定しない。


## 2026-11-03 Ministral対応追記（古い未検証記述より優先）

ユーザーの依頼でMinistralの修正とGPU動作確認を実施。
`configs/ministral-3-8b.yaml` に `config-format: mistral` と
`load-format: safetensors` を追加し、vLLM 0.19.1のHFネストarchitecture未指定問題を回避。
取得済みparams.jsonとHF分割重みをそのまま使用。依存関係やモデルは変更なし。
短文・23,433トークン長文・4件同時APIリクエストは成功。詳細はdocs/validation.md。
README/modelsの古いsample名も実在するministral-3-8b.yamlへ訂正。
検証用サーバーは確認終了後に停止。ユーザー自身で以下を実行して使う。

```bash
./scripts/start.sh configs/ministral-3-8b.yaml
```

configs/local.yamlはQwen用のまま。その他3モデルは依然として実推論未検証。


## 2026-11-03 GitHub公開準備追記

ユーザーが `https://github.com/kaiKyutech/vllm-server.git` を用意し、初回アップロードを明示的に依頼。
ローカルGitを初期化しoriginを設定。GitHub連携APIでmainへ初回登録する。
モデル・.venv・runtime・.tools・.env・configs/local.yaml・Jupyterチェックポイントは除外。
3090でclone後に試す手順はdocs/rtx3090.md。3090の実機検証はユーザー側でこれから実施。
既存CPUテスト7件、Python/シェル構文、公開対象の秘密情報パターン検査を通過。
今回の公開依頼は、将来の無条件なcommit/push許可ではない。
サーバー操作・GPU処理はこの公開作業では行っていない。
GitHub連携の認証と、このマシンのgit push用認証は別。後者は未設定。


## 2026-11-03 設定ファイル運用の統一（最新）

ユーザーの希望で、GitHubの起動YAMLはconfigs/*.sample.yamlのみ管理する。
Ministralをministral-3-8b.sample.yamlに改名。元のministral-3-8b.yamlはローカルに保持。
使用側は.sampleを外したコピーを作り、ハードに合わせて編集してstart.shへ渡す。
.gitignoreでconfigs直下の非sample YAMLを除外。generation/*.jsonは引き続き共有する。
README、モデル一覧、3090向け手順を更新。既存local.yamlとサーバーには触れていない。
古い記録にある非sampleの起動コマンドは、コピー先として使用できる。
