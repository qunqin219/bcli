"""ASR engines: SenseVoice-Small and Qwen3-ASR-0.6B.

Both run in a separate interpreter (the CLI itself never imports torch), so a
user can install either engine, both, or neither.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
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
    "groq": {
        "label": "Groq Whisper large-v3-turbo（云端，200×实时，免费额度 8h/天）",
        "remote": True,
        "key_env": "GROQ_API_KEY",
        "config_key": "groq_api_key",
        "base_url": "https://api.groq.com/openai/v1",
        "model_default": "whisper-large-v3-turbo",
        "model_url": "https://console.groq.com/docs/speech-to-text",
    },
    "groq-large": {
        "label": "Groq Whisper large-v3（云端，比 turbo 更准、稍慢）",
        "remote": True,
        "key_env": "GROQ_API_KEY",
        "config_key": "groq_api_key",
        "base_url": "https://api.groq.com/openai/v1",
        "model_default": "whisper-large-v3",
        "model_url": "https://console.groq.com/docs/speech-to-text",
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
    "whisper": "groq",
    "groq-whisper": "groq",
    "groq-turbo": "groq",
    "whisper-large": "groq-large",
    "whisper-large-v3": "groq-large",
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
    if spec.get("remote"):
        key = os.environ.get(spec["key_env"]) or config.get(spec["config_key"])
        return {
            "engine": engine,
            "label": spec["label"],
            "available": bool(key),
            "remote": True,
            "model": spec["model_default"],
            "base_url": spec["base_url"],
            "model_url": spec["model_url"],
            "reason": "" if key else f"未设置 {spec['key_env']}（或写进 ~/.config/bcli/config.json 的 {spec['config_key']}）",
        }
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


GROQ_MAX_BYTES = 24 * 1024 * 1024


def _multipart(fields: dict[str, str], file_field: str, data: bytes, filename: str, mime: str) -> tuple[bytes, str]:
    boundary = "----bcli" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode()
    out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("Groq 引擎需要 ffmpeg 压缩音频（apt install ffmpeg）")
    return exe


def _to_mp3(path: str, workdir: Path) -> Path:
    """16k 单声道 32kbps mp3：1 小时约 14MB，稳在 Groq 25MB 以内。"""
    src = Path(path)
    if src.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".ogg"} and src.stat().st_size <= GROQ_MAX_BYTES:
        return src
    out = workdir / (src.stem + ".groq.mp3")
    subprocess.run(
        [_ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-b:a", "32k", str(out)],
        check=True, timeout=3600,
    )
    if out.stat().st_size > GROQ_MAX_BYTES:
        raise RuntimeError(f"压缩后仍超过 25MB: {out.stat().st_size / 1e6:.1f}MB")
    return out


def _groq_transcribe(engine: str, paths: list[str], model: str) -> dict[str, Any]:
    spec = ENGINES[engine]
    key = os.environ.get(spec["key_env"]) or config.get(spec["config_key"])
    if not key:
        raise RuntimeError(f"缺少 {spec['key_env']}")
    workdir = Path(tempfile.mkdtemp(prefix="bcli-groq-"))
    items: list[dict[str, Any]] = []
    started = time.time()
    for raw_path in paths:
        audio = _to_mp3(raw_path, workdir)
        body, ctype = _multipart(
            {"model": model, "response_format": "verbose_json", "temperature": "0"},
            "file", audio.read_bytes(), audio.name, "audio/mpeg",
        )
        req = urllib.request.Request(
            f"{spec['base_url']}/audio/transcriptions", data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": ctype,
                # Groq 在 Cloudflare 后面，urllib 默认 UA 会被 1010 拦掉
                "User-Agent": "bili-cli/1.0 (+https://github.com/qunqin219/bcli)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:400]
            if exc.code == 429:
                raise RuntimeError(f"Groq 限流（免费额度 8h/天、文件 ≤25MB）：{detail}") from None
            raise RuntimeError(f"Groq 返回 {exc.code}: {detail}") from None
        segments = [
            {"start": round(s.get("start", 0), 3), "end": round(s.get("end", 0), 3),
             "text": (s.get("text") or "").strip()}
            for s in payload.get("segments") or []
        ]
        items.append({
            "file": raw_path,
            "text": (payload.get("text") or "").strip(),
            "language": payload.get("language", ""),
            "emotion": "",
            "segments": segments,
        })
    return {
        "model": model,
        "load_seconds": 0,
        "transcribe_seconds": round(time.time() - started, 2),
        "items": items,
        "remote": True,
    }


def transcribe(
    paths: list[str],
    engine: str | None = None,
    model: str | None = None,
    timeout: int = 7200,
) -> dict[str, Any]:
    key = resolve(engine)
    spec = ENGINES[key]
    info = describe(key)
    if spec.get("remote"):
        data = _groq_transcribe(key, paths, model or spec["model_default"])
        data["engine"] = key
        data["engine_label"] = spec["label"]
        return data
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
