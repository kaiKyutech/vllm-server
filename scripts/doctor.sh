#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_env
nvidia-smi
exec "$PYTHON" -u - <<'PY'
import importlib.metadata as m
import sys
print('Python:', sys.version, flush=True)
for name in ['vllm', 'torch', 'transformers', 'flashinfer-python']:
    print(f'{name}: {m.version(name)}', flush=True)
import torch
assert torch.cuda.is_available(), 'PyTorch がGPUを認識していません'
print('CUDA runtime:', torch.version.cuda, flush=True)
print('GPU:', torch.cuda.get_device_properties(0), flush=True)
a = torch.ones((32,32), device='cuda', dtype=torch.bfloat16)
assert (a @ a)[0,0].item() == 32
import vllm._C
print('BF16 GPU計算・vLLM拡張の読み込み: OK', flush=True)
PY
