"""Credential storage and QR login."""

from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .http import PASSPORT, UA, Client, NetworkError

CONFIG_DIR = Path(os.environ.get("BCLI_CONFIG_DIR", Path.home() / ".config" / "bcli"))
CREDENTIAL_FILE = CONFIG_DIR / "credential.json"


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------
def load_credential() -> dict[str, str]:
    """Saved credential, with environment variables taking precedence."""
    cred: dict[str, str] = {}
    if CREDENTIAL_FILE.exists():
        try:
            cred = json.loads(CREDENTIAL_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            cred = {}
    if os.environ.get("BCLI_SESSDATA"):
        cred["sessdata"] = os.environ["BCLI_SESSDATA"]
    if os.environ.get("BCLI_JCT"):
        cred["bili_jct"] = os.environ["BCLI_JCT"]
    if os.environ.get("BCLI_UID"):
        cred["dedeuserid"] = os.environ["BCLI_UID"]
    return cred


def save_credential(cred: dict[str, str]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "sessdata": cred.get("sessdata", ""),
        "bili_jct": cred.get("bili_jct", ""),
        "dedeuserid": cred.get("dedeuserid", ""),
        "ac_time_value": cred.get("ac_time_value", ""),
        "saved_at": int(time.time()),
    }
    CREDENTIAL_FILE.write_text(json.dumps(data, indent=2))
    CREDENTIAL_FILE.chmod(0o600)
    return CREDENTIAL_FILE


def clear_credential() -> None:
    if CREDENTIAL_FILE.exists():
        CREDENTIAL_FILE.unlink()


def client() -> Client:
    return Client(load_credential())


# --------------------------------------------------------------------------
# QR login
# --------------------------------------------------------------------------
def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def render_png(url: str, path: Path) -> bool:
    """Write the QR as PNG when the optional ``qrcode`` package is available."""
    try:
        import qrcode  # type: ignore
    except ImportError:
        return False
    img = qrcode.make(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return True


def qr_login(
    png: Path | None = None,
    timeout: int = 280,
    on_state: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Generate a login QR, poll until confirmed, persist the cookie set.

    Cookies arrive as Set-Cookie headers, so a CookieJar is required — reading
    the callback URL alone yields an empty SESSDATA.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def fetch(url: str) -> dict:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
        )
        with opener.open(req, timeout=20) as resp:
            return json.loads(resp.read())

    gen = fetch(f"{PASSPORT}/x/passport-login/web/qrcode/generate")
    if gen.get("code") != 0:
        raise NetworkError(f"生成二维码失败: {gen.get('message')}")
    qr_url = gen["data"]["url"]
    key = gen["data"]["qrcode_key"]

    if png:
        render_png(qr_url, png)

    deadline = time.time() + timeout
    last: int | None = None
    while time.time() < deadline:
        query = urllib.parse.urlencode({"qrcode_key": key, "source": "main-fe-header"})
        data = fetch(f"{PASSPORT}/x/passport-login/web/qrcode/poll?{query}").get("data") or {}
        code = data.get("code")
        if code != last and on_state:
            state = {0: "confirmed", 86038: "expired", 86090: "scanned", 86101: "waiting"}
            on_state(state.get(code if code is not None else -1, str(code)))
        last = code
        if code == 0:
            jars = {c.name: c.value for c in jar}
            cred = {
                "sessdata": jars.get("SESSDATA", ""),
                "bili_jct": jars.get("bili_jct", ""),
                "dedeuserid": jars.get("DedeUserID", ""),
                "ac_time_value": data.get("refresh_token", ""),
            }
            if not cred["sessdata"]:
                raise NetworkError("登录成功但未取到 SESSDATA")
            save_credential(cred)
            return cred
        if code == 86038:
            raise NetworkError("二维码已过期，请重新运行 bcli login")
        time.sleep(2)
    raise NetworkError("等待扫码超时")
