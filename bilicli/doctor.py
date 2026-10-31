"""`bili doctor`: self-diagnosis of network, auth, media and ASR setup."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__, config
from .auth import CREDENTIAL_FILE, client, load_credential
from .http import Client, NetworkError


def _check(name: str, ok: bool, detail: str = "", hint: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "hint": hint}


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("python", sys.version_info >= (3, 11), platform.python_version()))
    checks.append(_check("platform", True, f"{platform.system()} {platform.machine()}"))
    checks.append(_check("version", True, __version__))

    cred = load_credential()
    has_file = CREDENTIAL_FILE.exists()
    checks.append(
        _check(
            "credential-file",
            bool(cred.get("sessdata")),
            str(CREDENTIAL_FILE) if has_file else "不存在",
            "" if cred.get("sessdata") else "运行 bili login 扫码登录",
        )
    )

    c = client()
    try:
        nav = c.get("/x/web-interface/nav", auth_required=False)
        checks.append(_check("api", True, "api.bilibili.com 可达"))
    except NetworkError as exc:
        checks.append(_check("api", False, str(exc), "检查网络或代理设置"))
        nav = {}

    if cred.get("sessdata"):
        try:
            me = c.get("/x/web-interface/nav")
            checks.append(
                _check("auth", bool(me.get("isLogin")), f"已登录：{me.get('uname', '')}" if me.get("isLogin") else "凭证无效")
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("auth", False, str(exc), "重新运行 bili login"))
    else:
        checks.append(_check("auth", False, "未登录", "运行 bili login"))

    try:
        c.wbi_keys()
        checks.append(_check("wbi", True, "签名密钥可用"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("wbi", False, str(exc)))

    ffmpeg = shutil.which("ffmpeg")
    checks.append(
        _check("ffmpeg", bool(ffmpeg), ffmpeg or "未找到", "" if ffmpeg else "audio 切分需要 ffmpeg；或改用 --no-split")
    )

    asr_python = config.get("asr_python")
    asr_model = config.get("asr_model") or str(Path.home() / "models" / "SenseVoiceSmall")
    if asr_python:
        exists = Path(str(asr_python)).exists() or bool(shutil.which(str(asr_python)))
        checks.append(_check("asr-python", exists, str(asr_python), "" if exists else "检查 config.json 的 asr_python"))
    else:
        checks.append(_check("asr-python", True, "未配置（asr 命令会退回 python3）"))
    model_ok = Path(str(asr_model)).exists()
    checks.append(
        _check("asr-model", model_ok, str(asr_model), "" if model_ok else "hf download FunAudioLLM/SenseVoiceSmall --local-dir ~/models/SenseVoiceSmall")
    )

    from . import asr as asr_mod

    for info in asr_mod.list_engines()["engines"]:
        detail = f"{info['python']} → {info['model']}"
        checks.append(
            _check(
                f"asr-engine:{info['engine']}",
                info["available"],
                detail,
                "" if info["available"] else info["reason"],
            )
        )

    try:
        import qrcode  # noqa: F401

        checks.append(_check("qrcode(png)", True, "可生成二维码图片"))
    except ImportError:
        checks.append(_check("qrcode(png)", False, "未安装 [qr] extra", "pip install -e '.[qr]' 可保存 PNG 二维码"))

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    checks.append(_check("proxy", True, proxy or "未设置"))

    return {"version": __version__, "ok": all(c["ok"] for c in checks), "checks": checks}
