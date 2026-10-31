"""ASR engines: SenseVoice-Small and Qwen3-ASR-0.6B.

Both run in a separate interpreter (the CLI itself never imports torch), so a
user can install either engine, both, or neither.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import config

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

ENGINES: dict[str, dict[str, Any]] = {
    "sensevoice": {
        "label": "SenseVoice-Small（快，中文强，非自回归）",
        "python_key": "asr_python",
        "model_key": "asr_model",
        "worker_key": "asr_worker",
        "env": "BCLI_ASR_MODEL",
        "python_env": "BCLI_ASR_PYTHON",
        "worker": SCRIPTS / "asr_worker.py",
        "model_default": Path.home() / "models" / "SenseVoiceSmall",
        "model_url": "https://huggingface.co/FunAudioLLM/SenseVoiceSmall",
    },
    "qwen3-asr": {
        "label": "Qwen3-ASR-0.6B（中英混说更准，自回归，慢）",
        "python_key": "asr_qwen_python",
        "model_key": "asr_qwen_model",
        "worker_key": "asr_qwen_worker",
        "env": "BCLI_QWEN_ASR_MODEL",
        "python_env": "BCLI_QWEN_ASR_PYTHON",
        "worker": SCRIPTS / "asr_qwen_worker.py",
        "model_default": Path.home() / "models" / "Qwen3-ASR-0.6B",
        "model_url": "https://huggingface.co/Qwen/Qwen3-ASR-0.6B",
    },
}

ALIASES = {
    "sensevoice-small": "sensevoice",
    "sense-voice": "sensevoice",
    "sv": "sensevoice",
    "qwen": "qwen3-asr",
    "qwen3": "qwen3-asr",
    "qwen3_asr": "qwen3-asr",
    "qwen-asr": "qwen3-asr",
}


def _python(engine: str) -> str:
    spec = ENGINES[engine]
    value = config.get(spec["python_key"])
    if value:
        return str(value)
    # fall back to whatever python carries the engine's deps
    return shutil.which("python3") or "python3"


def _model(engine: str, override: str | None = None) -> Path:
    spec = ENGINES[engine]
    value = override or config.get(spec["model_key"]) or spec["model_default"]
    return Path(value).expanduser()


def describe(engine: str) -> dict[str, Any]:
    spec = ENGINES[engine]
    python = _python(engine)
    model = _model(engine)
    worker = Path(config.get(spec["worker_key"]) or spec["worker"])
    python_ok = Path(python).exists() or shutil.which(str(python)) is not None
    model_ok = model.exists()
    worker_ok = worker.exists()
    reason = ""
    if not python_ok:
        reason = f"解释器不存在: {python}"
    elif not worker_ok:
        reason = f"worker 不存在: {worker}"
    elif not model_ok:
        reason = f"模型目录不存在: {model}"
    return {
        "engine": engine,
        "label": spec["label"],
        "available": python_ok and worker_ok and model_ok,
        "python": python,
        "model": str(model),
        "worker": str(worker),
        "model_url": spec["model_url"],
        "reason": reason,
    }


def list_engines() -> dict[str, Any]:
    items = [describe(name) for name in ENGINES]
    usable = [i["engine"] for i in items if i["available"]]
    configured = config.get("asr_engine")
    default = configured if configured in ENGINES else (usable[0] if usable else "")
    return {"engines": items, "default": default, "available": usable}


def resolve(name: str | None = None) -> str:
    """Pick an engine: explicit name > config > first available > sensevoice."""
    if name and name != "auto":
        key = ALIASES.get(name.lower(), name.lower())
        if key not in ENGINES:
            raise ValueError(f"未知 ASR 引擎: {name}（可选: {', '.join(ENGINES)}）")
        info = describe(key)
        if not info["available"]:
            raise RuntimeError(f"引擎 {key} 不可用：{info['reason']}。装好后重试，或用 --engine 指定另一个。")
        return key
    configured = config.get("asr_engine")
    if configured and configured in ENGINES and describe(configured)["available"]:
        return configured
    for key in ENGINES:
        if describe(key)["available"]:
            return key
    raise RuntimeError(
        "没有可用的 ASR 引擎。装一个：pip install funasr torch（SenseVoice）或 pip install qwen-asr torch（Qwen3-ASR），"
        "再把 asr_python / asr_qwen_python 指到对应解释器。运行 `bili asr-engines` 查看检测结果。"
    )


def transcribe(
    paths: list[str],
    engine: str | None = None,
    model: str | None = None,
    timeout: int = 7200,
) -> dict[str, Any]:
    key = resolve(engine)
    spec = ENGINES[key]
    info = describe(key)
    if model:
        info["model"] = str(Path(model).expanduser())
    env = dict(os.environ)
    env[spec["env"]] = info["model"]
    proc = subprocess.run(
        [info["python"], info["worker"], *paths],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-800:] or f"{key} worker 失败")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if not payload.get("ok"):
        raise RuntimeError((payload.get("error") or {}).get("message", "ASR 失败"))
    data = payload["data"]
    data["engine"] = key
    data["engine_label"] = spec["label"]
    return data
