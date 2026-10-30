"""Minimal MCP server (stdio, JSON-RPC 2.0) exposing bili as agent tools.

Run `bili mcp` and point an MCP client at the process. Read-only tools only;
anything that mutates the account stays a deliberate CLI action.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from . import __version__, api, auth

PROTOCOL_VERSION = "2024-11-05"


def _tool(name: str, description: str, props: dict[str, Any], handler: Callable[[dict], Any]) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": props, "additionalProperties": False},
        "_handler": handler,
    }


def _int_prop(desc: str, default: int) -> dict:
    return {"type": "integer", "description": desc, "default": default}


WRITE_TOOLS = os.environ.get("BILI_MCP_WRITE") == "1"


def build_tools() -> list[dict]:
    tools = [
        _tool("bili_status", "登录状态与当前账号", {}, lambda a: _status()),
        _tool("bili_hot", "B站热门视频", {"limit": _int_prop("数量", 10)}, lambda a: api.hot(auth.client(), a.get("limit", 10))),
        _tool("bili_rank", "全站排行榜", {"limit": _int_prop("数量", 10)}, lambda a: api.rank(auth.client(), a.get("limit", 10))),
        _tool(
            "bili_search",
            "搜索视频或用户",
            {"keyword": {"type": "string"}, "type": {"type": "string", "enum": ["video", "user"]}, "limit": _int_prop("数量", 10)},
            lambda a: api.search(auth.client(), a["keyword"], a.get("type", "video"), 1, a.get("limit", 10)),
        ),
        _tool(
            "bili_video",
            "视频详情，可选字幕与评论",
            {"bvid": {"type": "string"}, "subtitle": {"type": "boolean"}, "comments": {"type": "boolean"}},
            lambda a: api.video(auth.client(), api.bvid_of(a["bvid"]), a.get("subtitle", False), a.get("comments", False)),
        ),
        _tool("bili_user", "UP 主资料", {"uid": {"type": "string"}}, lambda a: api.user(auth.client(), a["uid"])),
        _tool(
            "bili_user_videos",
            "UP 主投稿列表",
            {"uid": {"type": "string"}, "limit": _int_prop("数量", 10)},
            lambda a: api.user_videos(auth.client(), a["uid"], 1, a.get("limit", 10)),
        ),
        _tool(
            "bili_comments",
            "视频评论（第一页热门）",
            {"bvid": {"type": "string"}, "limit": _int_prop("数量", 20)},
            lambda a: _comments(a),
        ),
        _tool("bili_history", "观看历史", {"limit": _int_prop("数量", 20)}, lambda a: api.history(auth.client(), a.get("limit", 20))),
        _tool("bili_favorites", "收藏夹列表", {}, lambda a: api.favorites(auth.client())),
        _tool("bili_watch_later", "稍后再看", {"limit": _int_prop("数量", 20)}, lambda a: api.watch_later(auth.client(), a.get("limit", 20))),
        _tool("bili_feed", "关注动态", {"limit": _int_prop("数量", 20)}, lambda a: api.dynamic_feed(auth.client(), a.get("limit", 20))),
        _tool("bili_my_dynamics", "我的动态", {"limit": _int_prop("数量", 20)}, lambda a: api.my_dynamics(auth.client(), a.get("limit", 20))),
        _tool("bili_bangumi", "番剧信息", {"season_id": {"type": "string"}}, lambda a: _bangumi(a)),
        _tool(
            "bili_notifications",
            "消息中心（回复/@/点赞）",
            {"kind": {"type": "string", "enum": ["reply", "at", "like"]}, "limit": _int_prop("数量", 20)},
            lambda a: _notifications(a),
        ),
    ]
    tools += [
        _tool("bili_login", "生成登录二维码；action=start 返回 base64 PNG，action=status 查询扫码结果",
              {"action": {"type": "string", "enum": ["start", "status"]}},
              lambda a: _login(a)),
    ]
    if WRITE_TOOLS:
        tools += [
            _tool("bili_like", "点赞/取消点赞（写操作）",
                  {"bvid": {"type": "string"}, "undo": {"type": "boolean"}},
                  lambda a: api.like(auth.client(), api.bvid_of(a["bvid"]), a.get("undo", False))),
            _tool("bili_follow", "关注/取关（写操作）",
                  {"uid": {"type": "string"}, "undo": {"type": "boolean"}},
                  lambda a: api.follow(auth.client(), a["uid"], a.get("undo", False))),
        ]
    return tools


def _status() -> dict:
    cred = auth.load_credential()
    c = auth.client()
    info = None
    if c.logged_in:
        try:
            info = api.whoami(c)
        except Exception:  # noqa: BLE001
            info = None
    return {"authenticated": info is not None, "has_sessdata": bool(cred.get("sessdata")), "user": info}


def _comments(a: dict) -> dict:
    from . import social

    info = api.video(auth.client(), api.bvid_of(a["bvid"]))
    return social.comments(auth.client(), str(info["aid"]), "", a.get("limit", 20))


_QR_SESSION: dict[str, Any] = {}


def _login(a: dict) -> dict:
    """Two-step QR login: start returns a base64 PNG, status polls the same key."""
    import base64
    import http.cookiejar
    import io
    import urllib.parse
    import urllib.request

    from .http import PASSPORT, UA

    if a.get("action") == "start":
        req = urllib.request.Request(
            f"{PASSPORT}/x/passport-login/web/qrcode/generate",
            headers={"User-Agent": UA},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]
        _QR_SESSION["key"] = data["qrcode_key"]
        _QR_SESSION["jar"] = http.cookiejar.CookieJar()
        png = b""
        try:
            import qrcode

            buf = io.BytesIO()
            qrcode.make(data["url"]).save(buf, format="PNG")
            png = buf.getvalue()
        except Exception:
            png = b""
        return {"qrcode_key": data["qrcode_key"], "url": data["url"], "png_base64": base64.b64encode(png).decode()}

    key = _QR_SESSION.get("key")
    if not key:
        raise RuntimeError("先调用 action=start")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_QR_SESSION["jar"]))
    query = urllib.parse.urlencode({"qrcode_key": key, "source": "main-fe-header"})
    req = urllib.request.Request(f"{PASSPORT}/x/passport-login/web/qrcode/poll?{query}", headers={"User-Agent": UA})
    data = json.loads(opener.open(req, timeout=20).read()).get("data") or {}
    code = data.get("code")
    if code == 0:
        jar = {c.name: c.value for c in _QR_SESSION["jar"]}
        from .auth import save_credential

        save_credential({
            "sessdata": jar.get("SESSDATA", ""),
            "bili_jct": jar.get("bili_jct", ""),
            "dedeuserid": jar.get("DedeUserID", ""),
            "ac_time_value": data.get("refresh_token", ""),
        })
        _QR_SESSION.clear()
        return {"status": "confirmed", "uid": jar.get("DedeUserID", "")}
    return {"status": {86090: "scanned", 86038: "expired", 86101: "waiting"}.get(code, str(code))}


def _bangumi(a: dict) -> dict:
    from . import content

    return content.bangumi(auth.client(), season_id=a["season_id"])



def _notifications(a: dict) -> list:
    from . import social

    return social.messages(auth.client(), a.get("kind", "reply"), 1, a.get("limit", 20))


def _respond(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(request: dict, tools: dict[str, dict]) -> dict | None:
    method = request.get("method")
    req_id = request.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "bili", "version": __version__},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {k: v for k, v in tool.items() if not k.startswith("_")} for tool in tools.values()
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = tools.get(str(name))
        if not tool:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        try:
            result = tool["_handler"](arguments)
            text = json.dumps({"ok": True, "data": result}, ensure_ascii=False)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)}], "isError": True},
            }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve() -> int:
    tools = {tool["name"]: tool for tool in build_tools()}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _respond({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        response = handle(request, tools)
        if response is not None:
            _respond(response)
    return 0
