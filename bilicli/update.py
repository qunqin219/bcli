"""Self-update: check GitHub releases and replace the running binary."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__
from .http import UA, NetworkError

REPO = "qunqin219/bcli"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(value: str) -> tuple[int, ...]:
    """'v0.2.1' -> (0, 2, 1). Non-numeric suffixes are ignored."""
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def platform_asset() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        return "bili-linux-x64"
    if system == "darwin":
        return "bili-macos-arm64" if machine in ("arm64", "aarch64") else ""
    if system == "windows":
        return "bili-windows-x64.exe"
    return ""


def fetch_latest() -> dict[str, Any]:
    req = urllib.request.Request(
        API_LATEST,
        headers={"User-Agent": UA, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 - surfaced as a CLI error
        raise NetworkError(f"查询最新版本失败: {exc}") from exc


def check() -> dict[str, Any]:
    latest = fetch_latest()
    return {
        "current": __version__,
        "latest": (latest.get("tag_name") or "").lstrip("v"),
        "up_to_date": not is_newer(latest.get("tag_name", ""), __version__),
        "url": latest.get("html_url", ""),
        "asset": platform_asset(),
    }


def running_binary() -> Path | None:
    """Path of the executable when frozen by PyInstaller, else None."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def install_method() -> str:
    binary = running_binary()
    if binary is None:
        return "python"
    text = str(binary)
    if "/Cellar/" in text or text.startswith("/opt/homebrew/") or text.startswith("/usr/local/Cellar"):
        return "homebrew"
    return "binary"


def perform_update() -> dict[str, Any]:
    info = check()
    method = install_method()
    if info["up_to_date"]:
        return {**info, "updated": False, "method": method}

    if method == "homebrew":
        return {**info, "updated": False, "method": method, "hint": "brew upgrade bili"}
    if method == "python":
        return {
            **info,
            "updated": False,
            "method": method,
            "hint": "从源码安装：git pull && pip install -e . 或重新下载发布包",
        }

    binary = running_binary()
    if binary is None:  # method == "binary" implies frozen, but keep mypy honest
        raise NetworkError("无法定位当前可执行文件")
    asset = platform_asset()
    if not asset:
        return {**info, "updated": False, "method": method, "hint": "当前平台没有预编译二进制"}

    latest = fetch_latest()
    url = next((a["browser_download_url"] for a in latest.get("assets", []) if a["name"] == asset), "")
    if not url:
        raise NetworkError(f"发布里没有 {asset}")

    target = binary
    tmp = Path(tempfile.mkstemp(prefix="bili-update-", dir=str(target.parent))[1])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return {**info, "updated": True, "method": method, "path": str(target)}
