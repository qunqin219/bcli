"""Second-level replies, user dynamics, follow groups, bangumi follow list."""

from __future__ import annotations

from typing import Any

from .http import Client


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def replies(c: Client, aid: str, root: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
    data = c.get(
        "/x/v2/reply/reply",
        {"oid": aid, "root": root, "pn": page, "ps": min(limit, 49), "type": 1},
    )
    rows = data.get("replies") or []
    page_info = data.get("page") or {}
    return {
        "total": _int(page_info.get("count")),
        "items": [
            {
                "rpid": str(r.get("rpid_str") or r.get("rpid") or ""),
                "author": (r.get("member") or {}).get("uname", ""),
                "message": (r.get("content") or {}).get("message", ""),
                "like": _int(r.get("like")),
                "ctime": r.get("ctime", 0),
            }
            for r in rows[:limit]
        ],
    }


def delete_comment(c: Client, aid: str, rpid: str) -> dict[str, Any]:
    c.post("/x/v2/reply/del", {"oid": aid, "type": 1, "rpid": rpid})
    return {"rpid": rpid, "deleted": True}


def user_dynamics(c: Client, uid: str, offset: str = "", limit: int = 20) -> dict[str, Any]:
    params: dict[str, Any] = {"host_mid": uid, "timezone_offset": -480}
    if offset:
        params["offset"] = offset
    data = c.get("/x/polymer/web-dynamic/v1/feed/space", params, auth_required=True)
    from .api import _dynamic_item

    return {
        "items": [_dynamic_item(i) for i in (data.get("items") or [])[:limit]],
        "next_offset": data.get("offset") or "",
    }


def follow_tags(c: Client, uid: str) -> list[dict]:
    data = c.get("/x/relation/tags", {"vmid": uid}, auth_required=True)
    rows = data if isinstance(data, list) else data.get("list") or []
    return [
        {"tagid": t.get("tagid"), "name": t.get("name", ""), "count": _int(t.get("count"))}
        for t in rows
    ]


def tag_members(c: Client, uid: str, tagid: int, page: int = 1, limit: int = 20) -> dict[str, Any]:
    data = c.get(
        "/x/relation/tag",
        {"tagid": tagid, "pn": page, "ps": min(limit, 50), "vmid": uid},
        auth_required=True,
    )
    rows = data if isinstance(data, list) else data.get("list") or []
    return {
        "items": [
            {"uid": str(r.get("mid", "")), "name": r.get("uname", ""), "sign": (r.get("sign") or "")[:60]}
            for r in rows[:limit]
        ]
    }


def bangumi_followed(c: Client, uid: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
    data = c.get(
        "/x/space/bangumi/follow/list",
        {"type": 1, "vmid": uid, "pn": page, "ps": min(limit, 30), "follow_status": 0},
        referer=f"https://space.bilibili.com/{uid}/bangumi",
    )
    rows = data.get("list") or []
    return {
        "total": _int(data.get("total")),
        "items": [
            {
                "season_id": r.get("season_id"),
                "title": r.get("title", ""),
                "cover": r.get("cover", ""),
                "new_ep": (r.get("new_ep") or {}).get("index_show", ""),
            }
            for r in rows[:limit]
        ],
    }


def bangumi_follow(c: Client, season_id: str, undo: bool = False) -> dict[str, Any]:
    path = "/x/space/bangumi/follow/del" if undo else "/x/space/bangumi/follow/add"
    c.post(path, {"season_id": season_id})
    return {"season_id": season_id, "following": not undo}
