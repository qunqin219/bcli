"""HTTP layer: cookies, WBI signing, error mapping. Standard library only."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
API = "https://api.bilibili.com"
PASSPORT = "https://passport.bilibili.com"

# WBI mixin-key permutation table (fixed by the platform).
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


class ApiError(Exception):
    """Bilibili returned a non-zero code."""

    def __init__(self, code: int | str, message: str, action: str = ""):
        self.code = code
        self.message = message
        self.action = action
        super().__init__(f"{action + ': ' if action else ''}[{code}] {message}")


class AuthError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


class NetworkError(Exception):
    pass


class Client:
    def __init__(self, credential: dict[str, str] | None = None, timeout: int = 20):
        self.cookies: dict[str, str] = {}
        if credential:
            if credential.get("sessdata"):
                self.cookies["SESSDATA"] = credential["sessdata"]
            if credential.get("bili_jct"):
                self.cookies["bili_jct"] = credential["bili_jct"]
            if credential.get("dedeuserid"):
                self.cookies["DedeUserID"] = credential["dedeuserid"]
        self.timeout = timeout
        self._wbi: tuple[str, str] | None = None
        self._wbi_at = 0.0

    # -- headers ---------------------------------------------------------
    def headers(self, referer: str = "https://www.bilibili.com/") -> dict[str, str]:
        h = {
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        return h

    @property
    def logged_in(self) -> bool:
        return bool(self.cookies.get("SESSDATA"))

    # -- WBI signing -----------------------------------------------------
    def wbi_keys(self) -> tuple[str, str]:
        now = time.time()
        if self._wbi and now - self._wbi_at < 3600:
            return self._wbi
        payload = self.get("/x/web-interface/nav", auth_required=False)
        wbi = payload.get("wbi_img") or {}
        img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        if not img or not sub:
            raise NetworkError("无法获取 WBI 签名密钥")
        self._wbi, self._wbi_at = (img, sub), now
        return self._wbi

    def _mixin_key(self) -> str:
        img, sub = self.wbi_keys()
        raw = img + sub
        return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB if i < len(raw))[:32]

    def sign_wbi(self, params: dict[str, Any]) -> dict[str, str]:
        signed = {k: v for k, v in params.items() if v is not None}
        signed["wts"] = int(time.time())
        signed = {
            k: "".join(ch for ch in str(v) if ch not in "!'()*")
            for k, v in sorted(signed.items())
        }
        query = urllib.parse.urlencode(signed)
        signed["w_rid"] = hashlib.md5((query + self._mixin_key()).encode()).hexdigest()
        return signed

    # -- requests --------------------------------------------------------
    def _open(self, url: str, headers: dict[str, str]) -> bytes:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code}: {url.split('?')[0]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise NetworkError(f"{exc}: {url.split('?')[0]}") from exc

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        wbi: bool = False,
        auth_required: bool = False,
        referer: str = "https://www.bilibili.com/",
        host: str = API,
    ) -> dict[str, Any]:
        if auth_required and not self.logged_in:
            raise AuthError("not_authenticated", "请先运行 bcli login 登录")
        params = params or {}
        if wbi:
            params = self.sign_wbi(params)
        query = urllib.parse.urlencode(params)
        url = f"{host}{path}" + (f"?{query}" if query else "")
        raw = self._open(url, self.headers(referer))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NetworkError(f"响应不是 JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise NetworkError(f"响应格式异常: {path}")

        code = payload.get("code", 0)
        if code != 0:
            message = payload.get("message") or payload.get("msg") or "unknown error"
            if code in (-101, -111):
                raise AuthError(code, message, path)
            if code in (-404, 62002, 62004):
                raise NotFoundError(code, message, path)
            raise ApiError(code, message, path)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    # -- media -----------------------------------------------------------
    def download(self, url: str, out_path: str) -> int:
        """Download a media URL. Range is mandatory: plain GETs get HTTP 567."""
        import os

        headers = {
            "User-Agent": UA,
            "Referer": "https://www.bilibili.com/",
            "Accept": "*/*",
            "Range": "bytes=0-",
        }
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        req = urllib.request.Request(url, headers=headers)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp, open(out_path, "wb") as fh:
                total = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
                return total
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code}: 媒体下载失败") from exc
