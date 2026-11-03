# 動作確認

2026-11-02 にローカルAPIで検証した結果。

- 対象: A100 80GB PCIe の MIG 3g.40gb（利用可能40,192 MiB、42 SM）
- ドライバ: 570.86.15
- Python 3.12.9 / vLLM 0.19.1 / PyTorch 2.10.0+cu129 / Transformers 5.5.3
- モデル: Qwen/Qwen3.5-9B BF16
- revision: `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
- 初期検証時の保存先: `models/Qwen3.5-9B/`。その時点ではこのモデルだけを取得。
  後から取得した4モデルは [models.md](models.md) を参照。
- RTX 3090: 未検証。スクリプトは共通だが、このGPUでの動作・最適設定は未確認。
- Cloudflare: 既存のcloudflaredを利用。外部公開の実行・経路の測定は未実施。

## 通過した確認

- セットアップ再実行で固定済み179パッケージの監査が完了し、モデルの再取得は発生しない。
- `doctor.sh`: GPU認識、BF16行列積、vLLM拡張の読み込みに成功。
- `start.sh configs/local.yaml`: オフラインでローカルモデルを起動。
- コンテキスト上限32,768、同時処理上限32、バッチトークン上限16,384、VRAM使用率0.95。
- `/health` と `/v1/models` に正常応答。API上のモデル名は `qwen35-9b`。
- 短い日本語チャット: 入力20 / 出力35トークン、約5.41秒（初回リクエストを含む）。
- 長い日本語指示付き入力: **入力21,043 / 出力4トークン、約5.62秒**。
  繰り返しデータの末尾に置いた合言葉「青い鳥」を正しく回答した。
- `stream: false`、`temperature: 0`、thinkingなしで確認。
- 仮APIでbenchの同時実行上限、トークン集計、ウォームアップ除外、秘密情報の保存除外、HTTP失敗の記録と終了コードを確認。
- 最終版の全シェル・Pythonスクリプトの構文確認に成功。

実際のレスポンスは `runtime/smoke.json`、起動ログは `runtime/server.log`、
環境確認ログは `runtime/doctor.log`。これらの実行時ファイルはGit管理外。

## 短い合成入力による並列測定

```bash
./scripts/bench.sh --warmup --requests 16 --concurrency 1 4 8 16 \
  --max-tokens 64 --output runtime/bench-smoke.json
```

各並列数で16リクエスト。各出力64トークン、合計1,024出力トークン。
全64リクエストがHTTP成功。出力は意図的に64トークン上限で終了している。

| クライアント並列数 | 16件の総時間 | 出力トークン/秒（全体） |
|---:|---:|---:|
| 1 | 23.37秒 | 43.8 |
| 4 | 6.43秒 | 159.3 |
| 8 | 3.38秒 | 302.7 |
| 16 | 1.93秒 | 531.0 |

これは約50トークンの短い入力で測定ツールと並列処理の動作を確かめた結果であり、
**20K入力の実験の性能・最適並列数を示すものではない**。
入力先頭に固有IDを付け、prefix cachingは無効にした。IDのトークン化により入力トークン数は少し異なる。
実際の実験JSONLを使い、同じ実験セットの総時間で今後調整する。

## 起動時のメモリ・所要時間

- モデル読み込みのGPU使用量: 約16.8 GiB。
- KVキャッシュ用に割り当て可能なメモリ: 起動ログで約18.12 GiB。
- 起動ログの32,768トークン時の推定最大並列度: 約17.03x。性能保証や実測最適値ではない。
- 重みの読み込み: 約27秒。初回torch.compile: 約72秒。
- 初回engine初期化（プロファイル・キャッシュ・ウォームアップ等）: 約225秒。
- ネットワーク経由のsrv11へのパッケージ初回配置は約15分半かかった。
  2回目のセットアップは179パッケージの監査が約0.13秒で完了した。
- 初期構築時のディスク使用量: `du -h` で約29G（モデル約19G、環境約11G、runtime約243M、丸め表示）。
  4モデル追加後の計測では約81G。いずれも過去の計測値であり、現在値ではない。

CUDA Toolkitやドライバ、他のプロジェクトの環境は変更していない。
作成した環境・モデル・ツールは `vllm-server/` 内に保存。
実行時のキャッシュと一時ファイルも `runtime/` 配下を指定する。
Docker再起動そのものの試験は行っていない。再起動後は同じPython 3.12とGPUドライバが
コンテナのベース環境に提供されることが前提。

## サーバー生成既定値の追加検証

2026-11-02にvLLM標準ミドルウェアによる既定値の補完を追加し、Qwenサーバーを再起動。
thinkingの省略時動作は公式テンプレートのまま維持する。

- CPU単体テスト7件: 公式thinking既定の維持、非thinkingへの推奨値切替、クライアントの明示的な0、
  nullの扱い、サーバー上書き値、分割されたUTF-8 HTTP本文、Content-Length、認証ヘッダー、
  不正JSONの通常API検証への引き継ぎ、他ルートの非変更を確認。
- 実際のChat Completionsで、同一入力・seedを用いて、生成パラメータを省略した応答と
  推奨値をすべて明示した応答の本文・reasoning・トークン数が一致した。
- 上記はthinking省略時と明示OFF時の両方で通過。
- クライアントのtemperature=0 / presence_penalty=0 / top_k=0の明示指定でも正常応答。
- 証跡は `runtime/generation-defaults-validation.json`。
- 以前提示されたCloudflareのURLへのhealth確認はHTTP 530だった。
  ローカルAPIは正常。Cloudflareプロセスは停止・再起動・設定変更していない。

他の4モデルは取得ファイルの存在とサイズ一致・重複形式除外を確認したが、実推論は未検証。


## Ministral 3 8B BF16（2026-11-03）

同じA100 MIG環境・固定済みvLLM 0.19.1で実推論を検証。
`./scripts/start.sh configs/ministral-3-8b.yaml` を使用。

- 原因: HF configの`text_config.architectures`がNoneで、Mistral3ラッパーの内部モデル初期化に失敗。
- 対応: `config-format: mistral`で取得済み`params.json`を読み、
  `load-format: safetensors`で取得済みHF分割重みを使用。
  Mistral専用のYaRN・attention scalingを保持し、PixtralForConditionalGeneration経由で読み込む。
- モデル・依存バージョン・配布元config.jsonは変更せず、再ダウンロードなし。
- コンテキスト上限32,768、同時処理上限32、バッチトークン上限16,384で起動成功。
- GPUモデル読み込み15.88 GiB、重み読込32.60秒。初回コンパイル54.05秒。
- `/v1/models`のモデル名`ministral-3-8b`を確認。
- 生成条件省略の日本語質問に「日本の首都は東京」と回答（入力15 / 出力11、3.385秒）。
- temperature=0の計算17+25に「42」と回答。
- 長文入力23,433トークンの末尾の合言葉「青い鳥」に正答（出力4、6.334秒）。
  合成繰り返し資料での確認であり、一般的な長文理解性能の評価ではない。
- 4リクエスト同時送信で全件成功し、計算結果も一致。
- 証跡: `runtime/ministral-validation.log`、`runtime/ministral-smoke.json`、
  `runtime/ministral-concurrent-smoke.json`。
- 画像入力、32件同時負荷、実データの最適並列数、3090は未検証。

Ministralは専用YAMLを明示して起動する。`configs/local.yaml`はQwen用のまま。
