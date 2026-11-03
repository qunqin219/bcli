"""HTTP layer: cookies, WBI signing, error mapping. Standard library only."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
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
    def __init__(
        self,
        credential: dict[str, str] | None = None,
        timeout: int = 20,
        retries: int | None = None,
    ):
        if retries is None:
            try:
                retries = int(os.environ.get("BILI_RETRIES", "2"))
            except ValueError:
                retries = 2
        self.cookies: dict[str, str] = {}
        if credential:
            if credential.get("sessdata"):
                self.cookies["SESSDATA"] = credential["sessdata"]
            if credential.get("bili_jct"):
                self.cookies["bili_jct"] = credential["bili_jct"]
            if credential.get("dedeuserid"):
                self.cookies["DedeUserID"] = credential["dedeuserid"]
        self.timeout = timeout
        self.retries = max(0, retries)
        try:
            self.rate = float(os.environ.get("BILI_RATE", "5"))
        except ValueError:
            self.rate = 5.0
        self._last_request = 0.0
        self.cache_ttl = int(os.environ.get("BILI_CACHE_TTL", "0"))
        self._wbi: tuple[str, str] | None = None
        self._wbi_at = 0.0
        self._buvid_tried = False

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

    # -- anonymous device id ---------------------------------------------
    def _ensure_buvid(self) -> None:
        """匿名请求也带 buvid3/buvid4，否则 view/comments 这类接口会 412/-352 风控。

        buvid 来自 /x/frontend/finger/spi，缓存在配置目录 7 天。
        """
        if self.logged_in or self.cookies.get("buvid3") or self._buvid_tried:
            return
        self._buvid_tried = True
        cache = Path(os.environ.get("BCLI_CONFIG_DIR", Path.home() / ".config" / "bcli")) / "buvid.json"
        try:
            cached = json.loads(cache.read_text())
            if cached.get("buvid3") and time.time() - float(cached.get("ts", 0)) < 7 * 86400:
                self.cookies["buvid3"] = cached["buvid3"]
                if cached.get("buvid4"):
                    self.cookies["buvid4"] = cached["buvid4"]
                return
        except (OSError, ValueError):
            pass
        try:
            payload = json.loads(self._open(f"{API}/x/frontend/finger/spi", self.headers(), retries=1))
            data = payload.get("data") or {}
            b3, b4 = data.get("b_3") or "", data.get("b_4") or ""
            if not b3:
                return
            self.cookies["buvid3"] = b3
            if b4:
                self.cookies["buvid4"] = b4
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"buvid3": b3, "buvid4": b4, "ts": time.time()}))
        except Exception:  # noqa: BLE001 - 匿名兜底失败不该阻断请求
            pass

    # -- WBI signing -----------------------------------------------------
    def wbi_keys(self) -> tuple[str, str]:
        now = time.time()
        if self._wbi and now - self._wbi_at < 3600:
            return self._wbi
        # /nav answers code -101 for anonymous callers but still carries wbi_img,
        # so parse the raw response instead of going through get().
        raw = self._open(f"{API}/x/web-interface/nav", self.headers())
        payload = json.loads(raw)
        wbi = (payload.get("data") or {}).get("wbi_img") or {}
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
    #: HTTP statuses worth retrying: rate limiting, anti-scraping, transient 5xx.
    RETRY_STATUS = frozenset({412, 429, 500, 502, 503, 504})

    def _sleep_backoff(self, attempt: int, retry_after: str | None = None) -> None:
        import random

        if retry_after:
            try:
                time.sleep(min(float(retry_after), 30))
                return
            except ValueError:
                pass
        delay = min(0.5 * (2**attempt), 8) + random.uniform(0, 0.25)
        time.sleep(delay)

    def _throttle(self) -> None:
        if self.rate <= 0:
            return
        gap = 1.0 / self.rate
        wait = self._last_request + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def _cache_path(self, url: str) -> Path:
        import hashlib
        import tempfile

        root = Path(os.environ.get("BILI_CACHE_DIR", Path(tempfile.gettempdir()) / "bili-cache"))
        root.mkdir(parents=True, exist_ok=True)
        return root / (hashlib.md5(url.encode()).hexdigest() + ".cache")

    def _open(self, url: str, headers: dict[str, str], *, retries: int | None = None) -> bytes:
        """GET with bounded retries. Only safe because GET is idempotent."""
        if self.cache_ttl > 0:
            cached = self._cache_path(url)
            if cached.exists() and time.time() - cached.stat().st_mtime < self.cache_ttl:
                return cached.read_bytes()
        attempts = (self.retries if retries is None else retries) + 1
        last_error = ""
        for attempt in range(attempts):
            self._throttle()
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    encoding = (resp.headers.get("Content-Encoding") or "").lower()
                if encoding == "gzip":
                    import gzip
                    data = gzip.decompress(raw)
                elif encoding == "deflate":
                    import zlib
                    try:
                        data = zlib.decompress(raw)
                    except zlib.error:
                        data = zlib.decompress(raw, -zlib.MAX_WBITS)
                else:
                    data = raw
                if self.cache_ttl > 0 and len(data) < 2_000_000:
                    try:
                        self._cache_path(url).write_bytes(data)
                    except OSError:
                        pass
                return data
            except urllib.error.HTTPError as exc:
                if exc.code in self.RETRY_STATUS and attempt < attempts - 1:
                    self._sleep_backoff(attempt, exc.headers.get("Retry-After"))
                    last_error = f"HTTP {exc.code}"
                    continue
                raise NetworkError(f"HTTP {exc.code}: {url.split('?')[0]}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < attempts - 1:
                    self._sleep_backoff(attempt)
                    last_error = str(exc)
                    continue
                raise NetworkError(f"{exc}: {url.split('?')[0]}") from exc
        raise NetworkError(f"{last_error or '重试耗尽'}: {url.split('?')[0]}")

    def _parse(self, raw: bytes, path: str) -> Any:
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
        # Most endpoints use "data"; the PGC/bangumi family uses "result".
        data = payload.get("data")
        if data is None:
            data = payload.get("result")
        return data if data is not None else {}

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        wbi: bool = False,
        auth_required: bool = False,
        referer: str = "https://www.bilibili.com/",
        host: str = API,
    ) -> Any:
        if auth_required and not self.logged_in:
            raise AuthError("not_authenticated", "请先运行 bili login 登录")
        self._ensure_buvid()
        params = params or {}
        if wbi:
            params = self.sign_wbi(params)
        query = urllib.parse.urlencode(params)
        url = f"{host}{path}" + (f"?{query}" if query else "")
        return self._parse(self._open(url, self.headers(referer)), path)

    def post(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        *,
        auth_required: bool = True,
        referer: str = "https://www.bilibili.com/",
    ) -> Any:
        """Form POST with the CSRF token. Write endpoints all require bili_jct."""
        if auth_required and not self.logged_in:
            raise AuthError("not_authenticated", "请先运行 bili login 登录")
        jct = self.cookies.get("bili_jct")
        if not jct:
            raise AuthError("missing_csrf", "缺少 bili_jct，请重新扫码登录")
        body = dict(data or {})
        body["csrf"] = jct
        headers = self.headers(referer)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Origin"] = "https://www.bilibili.com"
        req = urllib.request.Request(
            f"{API}{path}",
            data=urllib.parse.urlencode(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code}: {path}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise NetworkError(f"{exc}: {path}") from exc
        return self._parse(raw, path)

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
