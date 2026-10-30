"""Import Bilibili cookies from a local browser profile."""

from __future__ import annotations

import glob
import os
import sqlite3
from pathlib import Path
from typing import Any

from .auth import save_credential

NAMES = {"SESSDATA", "bili_jct", "DedeUserID"}


def _firefox_profiles() -> list[Path]:
    roots = [
        Path.home() / ".mozilla" / "firefox",
        Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles",
    ]
    out: list[Path] = []
    for root in roots:
        if root.exists():
            out.extend(Path(p) for p in glob.glob(str(root / "*" / "cookies.sqlite")))
    return out


def _chrome_profiles() -> list[Path]:
    roots = [
        Path.home() / ".config" / "google-chrome",
        Path.home() / ".config" / "microsoft-edge",
        Path.home() / ".config" / "chromium",
        Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
        Path.home() / "Library" / "Application Support" / "Microsoft Edge",
    ]
    out: list[Path] = []
    for root in roots:
        if root.exists():
            out.extend(Path(p) for p in glob.glob(str(root / "*/Cookies")))
    return out


def _from_firefox(path: Path) -> dict[str, str]:
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    try:
        rows = con.execute(
            "select name, value from moz_cookies where host like '%bilibili.com'"
        ).fetchall()
    finally:
        con.close()
    return {name: value for name, value in rows if name in NAMES}


def _from_chrome(path: Path) -> dict[str, str]:
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    try:
        rows = con.execute(
            "select name, value, encrypted_value from cookies where host_key like '%bilibili.com'"
        ).fetchall()
    finally:
        con.close()
    out: dict[str, str] = {}
    for name, value, encrypted in rows:
        if name not in NAMES:
            continue
        if value:
            out[name] = value
        elif encrypted and not bytes(encrypted).startswith(b"v10"):
            out[name] = bytes(encrypted).decode("utf-8", "ignore")
    return out


def import_from(browser: str = "firefox", profile: str = "") -> dict[str, Any]:
    candidates = _firefox_profiles() if browser == "firefox" else _chrome_profiles()
    if profile:
        candidates = [Path(profile)]
    if not candidates:
        raise FileNotFoundError(f"没找到 {browser} 的 cookie 数据库，可用 --profile 指定路径")

    errors: list[str] = []
    for path in candidates:
        try:
            cookies = _from_firefox(path) if browser == "firefox" else _from_chrome(path)
        except sqlite3.DatabaseError as exc:
            errors.append(f"{path}: {exc}")
            continue
        if cookies.get("SESSDATA"):
            cred = {
                "sessdata": cookies.get("SESSDATA", ""),
                "bili_jct": cookies.get("bili_jct", ""),
                "dedeuserid": cookies.get("DedeUserID", ""),
                "ac_time_value": "",
            }
            saved = save_credential(cred)
            return {"browser": browser, "source": str(path), "saved": str(saved)}

    if browser == "chrome":
        raise RuntimeError(
            "Chrome/Edge 的 cookie 在 Linux/macOS 上通常用系统密钥加密（v10），标准库无法解密；"
            "请改用 Firefox，或用 BCLI_SESSDATA 环境变量。"
        )
    raise RuntimeError("没找到有效的 Bilibili cookie" + (f"（{'; '.join(errors)}）" if errors else ""))
