"""Transcribe audio files with Qwen3-ASR-0.6B and print one JSON envelope.

Run with an environment that has torch + qwen-asr installed, e.g.:
    /path/to/qwen-env/bin/python scripts/asr_qwen_worker.py a.wav b.wav

Model directory: $BCLI_QWEN_ASR_MODEL (default ~/models/Qwen3-ASR-0.6B)
dtype: $BCLI_QWEN_ASR_DTYPE (float32 | bfloat16 | float16, default float32)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DTYPES = {"float32": "float32", "bf16": "bfloat16", "bfloat16": "bfloat16", "float16": "float16", "fp16": "float16"}


def main(paths: list[str]) -> int:
    model_dir = os.environ.get("BCLI_QWEN_ASR_MODEL") or str(Path.home() / "models" / "Qwen3-ASR-0.6B")
    dtype_name = DTYPES.get(os.environ.get("BCLI_QWEN_ASR_DTYPE", "float32"), "float32")
    try:
        import torch
        from qwen_asr import Qwen3ASRModel
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": {"code": "missing_dependency", "message": str(exc)}}))
        return 1

    if not Path(model_dir).exists():
        print(json.dumps({"ok": False, "error": {"code": "missing_model", "message": f"模型目录不存在: {model_dir}"}}))
        return 1

    started = time.time()
    model = Qwen3ASRModel.from_pretrained(
        model_dir,
        dtype=getattr(torch, dtype_name),
        device_map="cpu",
        max_new_tokens=2048,
    )
    load_seconds = round(time.time() - started, 2)

    t0 = time.time()
    results = model.transcribe(audio=list(paths), language=None)
    elapsed = max(time.time() - t0, 0.001)

    items = []
    for path, res in zip(paths, results):
        text = getattr(res, "text", "") or ""
        items.append(
            {
                "file": path,
                "text": text.strip(),
                "language": getattr(res, "language", "") or "",
            }
        )

    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": "1",
                "data": {
                    "model": model_dir,
                    "dtype": dtype_name,
                    "load_seconds": load_seconds,
                    "transcribe_seconds": round(elapsed, 2),
                    "items": items,
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
