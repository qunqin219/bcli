"""Transcribe audio files with SenseVoice-Small and print one JSON envelope.

Run with the environment that has funasr + torch installed, e.g.:
    /root/venvs/sensevoice/bin/python scripts/asr_worker.py a.wav b.wav
Model directory: $BCLI_ASR_MODEL (default /root/models/SenseVoiceSmall)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

TAG_RE = re.compile(r"<\|[^|]*\|>")


def main(paths: list[str]) -> int:
    model_dir = os.environ.get("BCLI_ASR_MODEL", "/root/models/SenseVoiceSmall")
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

    results = []
    for path in paths:
        t0 = time.time()
        out = model.generate(input=path, cache={}, language="auto", use_itn=True, batch_size_s=60)
        text = TAG_RE.sub("", out[0].get("text", "")).strip() if out else ""
        tags = re.findall(r"<\|([^|]*)\|>", out[0].get("text", "")) if out else []
        results.append(
            {
                "file": path,
                "text": text,
                "language": tags[0] if tags else "",
                "emotion": tags[1] if len(tags) > 1 else "",
                "seconds": round(time.time() - t0, 2),
            }
        )

    print(
        json.dumps(
            {"ok": True, "schema_version": "1", "data": {"model": model_dir, "load_seconds": load_seconds, "items": results}},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
