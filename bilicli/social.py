"""Social features: notifications, follow lists, comment pagination and actions."""

from __future__ import annotations

from typing import Any

from .http import Client


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def unread(c: Client) -> dict[str, int]:
    data = c.get("/x/msgfeed/unread", wbi=True, auth_required=True)
    return {k: _int(v) for k, v in data.items() if isinstance(v, (int, str))}


def messages(c: Client, kind: str = "reply", page: int = 1, limit: int = 20) -> list[dict]:
    if kind not in ("reply", "at", "like"):
        raise ValueError("kind 只能是 reply / at / like")
    data = c.get(
        f"/x/msgfeed/{kind}",
        {"pn": page, "ps": min(limit, 20)},
        wbi=True,
        auth_required=True,
    )
    items = data.get("items") or []
    return [
        {
            "id": item.get("id"),
            "user": (item.get("user") or {}).get("nickname", ""),
            "title": item.get("title", ""),
            "text": (item.get("item") or {}).get("source_content", "") or item.get("reply_content", ""),
            "url": (item.get("item") or {}).get("uri", ""),
            "time": item.get("at_time") or item.get("time", 0),
            "unread": bool(item.get("is_unread", False)),
        }
        for item in items[:limit]
    ]


def followings(c: Client, uid: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
    data = c.get("/x/relation/followings", {"vmid": uid, "pn": page, "ps": min(limit, 50)}, auth_required=True)
    rows = data.get("list") or []
    return {
        "total": _int(data.get("total")),
        "items": [
            {
                "uid": str(r.get("mid", "")),
                "name": r.get("uname", ""),
                "sign": (r.get("sign") or "")[:60],
                "official": (r.get("official_verify") or {}).get("desc", ""),
            }
            for r in rows[:limit]
        ],
    }


def fans(c: Client, uid: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
    data = c.get("/x/relation/fans", {"vmid": uid, "pn": page, "ps": min(limit, 50)}, auth_required=True)
    rows = data.get("list") or []
    return {
        "total": _int(data.get("total")),
        "items": [
            {
                "uid": str(r.get("mid", "")),
                "name": r.get("uname", ""),
                "sign": (r.get("sign") or "")[:60],
            }
            for r in rows[:limit]
        ],
    }


def comments(c: Client, aid: str, cursor: str = "", limit: int = 20) -> dict[str, Any]:
    params = {"oid": aid, "type": 1, "mode": 3, "ps": min(limit, 49), "next": cursor or 0}
    data = c.get("/x/v2/reply/wbi/main", params, wbi=True)
    replies = (data.get("replies") or [])[:limit]
    cur = data.get("cursor") or {}
    return {
        "items": [
            {
                "rpid": str(r.get("rpid_str") or r.get("rpid") or ""),
                "author": (r.get("member") or {}).get("uname", ""),
                "uid": str((r.get("member") or {}).get("mid", "")),
                "message": (r.get("content") or {}).get("message", ""),
                "like": _int(r.get("like")),
                "replies": _int(r.get("rcount")),
                "ctime": r.get("ctime", 0),
            }
            for r in replies
        ],
        "next": cur.get("next", 0),
        "is_end": bool(cur.get("is_end", False)),
    }


def reply_comment(c: Client, bvid: str, message: str, root: str = "", parent: str = "") -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    data = c.post(
        "/x/v2/reply/add",
        {
            "oid": info.get("aid"),
            "type": 1,
            "message": message,
            "root": root,
            "parent": parent or root,
            "plat": 1,
        },
    )
    return {"bvid": bvid, "rpid": str(data.get("rpid_str") or data.get("rpid") or "")}


def like_comment(c: Client, bvid: str, rpid: str, undo: bool = False) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    c.post(
        "/x/v2/reply/action",
        {"oid": info.get("aid"), "type": 1, "rpid": rpid, "action": 0 if undo else 1},
    )
    return {"rpid": rpid, "liked": not undo}
