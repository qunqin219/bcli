"""Minimal WebSocket client for Bilibili live danmaku (standard library only)."""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
import urllib.request
import zlib
from typing import Any, Iterator

from .http import UA

CONF_URL = "https://api.live.bilibili.com/room/v1/Danmu/getConf?room_id={room_id}&player=web&platform=web"


def _handshake(host: str, cookie: str = "") -> ssl.SSLSocket:
    raw = socket.create_connection((host, 443), timeout=15)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    lines = [
        "GET /sub HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "Origin: https://live.bilibili.com",
    ]
    if cookie:
        lines.append(f"Cookie: {cookie}")
    lines.append(f"User-Agent: {UA}")
    request = "\r\n".join(lines) + "\r\n\r\n"
    sock.sendall(request.encode())
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("WebSocket 握手失败")
        response += chunk
    status = response.split(b"\r\n", 1)[0].decode("latin-1")
    if "101" not in status:
        raise ConnectionError(f"WebSocket 握手被拒绝: {status}")
    return sock


def _pack(op: int, body: bytes) -> bytes:
    return struct.pack(">IHHII", 16 + len(body), 16, 1, op, 1) + body


def _send(sock: ssl.SSLSocket, op: int, body: bytes) -> None:
    payload = _pack(op, body)
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    length = len(payload)
    if length < 126:
        header = struct.pack(">BB", 0x81, 0x80 | length)
    elif length < (1 << 16):
        header = struct.pack(">BBH", 0x81, 0x80 | 126, length)
    else:
        header = struct.pack(">BBQ", 0x81, 0x80 | 127, length)
    sock.sendall(header + mask + masked)


def _read_exact(sock: ssl.SSLSocket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("连接已关闭")
        buf += chunk
    return buf


def _read_frame(sock: ssl.SSLSocket) -> bytes:
    first = _read_exact(sock, 2)
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(sock, 8))[0]
    mask = _read_exact(sock, 4) if masked else b""
    data = _read_exact(sock, length)
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return data


def _walk(data: bytes) -> Iterator[dict[str, Any]]:
    """Yield JSON messages, inflating nested zlib batches (protover 2)."""
    offset = 0
    while offset + 16 <= len(data):
        total, header_len, ver, op, _seq = struct.unpack(">IHHII", data[offset : offset + 16])
        if total < 16 or header_len < 16:
            break
        body = data[offset + header_len : offset + total]
        offset += total
        if ver == 2:
            try:
                yield from _walk(zlib.decompress(body))
            except zlib.error:
                continue
        elif op == 5:
            for line in body.decode("utf-8", "ignore").split("\x00"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue


def _danmaku(message: dict[str, Any]) -> dict[str, Any] | None:
    if "DANMU_MSG" not in (message.get("cmd") or ""):
        return None
    info = message.get("info") or []
    if len(info) < 3 or not isinstance(info[1], str):
        return None
    user = info[2][1] if isinstance(info[2], list) and len(info[2]) > 1 else ""
    return {"user": user, "text": info[1], "time": time.time()}


def stream(room_id: str, seconds: int = 60, limit: int = 100) -> dict[str, Any]:
    conf_req = urllib.request.Request(CONF_URL.format(room_id=room_id), headers={"User-Agent": UA})
    conf = json.loads(urllib.request.urlopen(conf_req, timeout=20).read())
    data = conf.get("data") or {}
    token = data.get("token", "")
    host = data.get("host") or "broadcastlv.chat.bilibili.com"

    from .auth import load_credential

    cred = load_credential()
    cookie = ""
    # Anonymous auth is the stable path; a uid without a matching buvid gets the
    # connection closed by the server.
    uid = 0

    sock = _handshake(host)
    collected: list[dict[str, Any]] = []
    try:
        auth = {"uid": uid, "roomid": int(room_id), "protover": 2, "platform": "web", "type": 2, "key": token}
        _send(sock, 7, json.dumps(auth).encode())
        _send(sock, 2, b"{}")
        sock.settimeout(5)
        deadline = time.time() + seconds
        last_beat = time.time()
        while time.time() < deadline and len(collected) < limit:
            if time.time() - last_beat > 25:
                _send(sock, 2, b"{}")
                last_beat = time.time()
            try:
                payload = _read_frame(sock)
            except (socket.timeout, TimeoutError):
                continue
            for message in _walk(payload):
                item = _danmaku(message)
                if item:
                    collected.append(item)
                    if len(collected) >= limit:
                        break
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return {"room_id": room_id, "count": len(collected), "items": collected}
