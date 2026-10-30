"""Transcribe audio files with SenseVoice-Small and print one JSON envelope.

Run with the environment that has funasr + torch installed, e.g.:
    /path/to/asr-env/bin/python scripts/asr_worker.py a.wav b.wav
Model directory: $BCLI_ASR_MODEL (default ~/models/SenseVoiceSmall)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

TAG_RE = re.compile(r"<\|[^|]*\|>")


def main(paths: list[str]) -> int:
    model_dir = os.environ.get("BCLI_ASR_MODEL") or str(Path.home() / "models" / "SenseVoiceSmall")
    try:
        from funasr import AutoModel
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": {"code": "missing_dependency", "message": str(exc)}}))
        return 1

    started = time.time()
    model = AutoModel(
        model=model_dir,
        disable_update=True,
        trust_remote_code=False,
        device="cpu",
    )
    load_seconds = round(time.time() - started, 2)

    # One batched call: funasr splits by batch_size_s, which is faster than
    # running the model per file.
    t0 = time.time()
    outputs = model.generate(input=list(paths), cache={}, language="auto", use_itn=True, batch_size_s=120)
    elapsed = max(time.time() - t0, 0.001)
    results = []
    for path, out in zip(paths, outputs):
        raw = out.get("text", "") if isinstance(out, dict) else ""
        tags = re.findall(r"<\|([^|]*)\|>", raw)
        results.append(
            {
                "file": path,
                "text": TAG_RE.sub("", raw).strip(),
                "language": tags[0] if tags else "",
                "emotion": tags[1] if len(tags) > 1 else "",
            }
        )

    print(
        json.dumps(
            {"ok": True, "schema_version": "1", "data": {"model": model_dir, "load_seconds": load_seconds, "transcribe_seconds": round(elapsed, 2), "items": results}},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
