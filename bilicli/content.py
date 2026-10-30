"""Content types beyond plain videos: bangumi, articles, collections."""

from __future__ import annotations

from typing import Any

from .http import Client


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def bangumi(c: Client, season_id: str | None = None, ep_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if season_id:
        params["season_id"] = season_id
    elif ep_id:
        params["ep_id"] = ep_id
    else:
        raise ValueError("需要 season_id 或 ep_id")
    data = c.get("/pgc/view/web/season", params, referer="https://www.bilibili.com/bangumi/")
    rating = data.get("rating") or {}
    return {
        "season_id": data.get("season_id"),
        "title": data.get("title", ""),
        "subtitle": data.get("subtitle", ""),
        "cover": data.get("cover", ""),
        "evaluate": (data.get("evaluate") or "")[:300],
        "rating": {"score": rating.get("score", 0), "count": _int(rating.get("count"))},
        "stat": {
            "favorites": _int((data.get("stat") or {}).get("favorites")),
            "views": _int((data.get("stat") or {}).get("views")),
            "danmakus": _int((data.get("stat") or {}).get("danmakus")),
        },
        "episodes": [
            {
                "ep_id": ep.get("id"),
                "title": ep.get("title", ""),
                "long_title": ep.get("long_title", ""),
                "cover": ep.get("cover", ""),
            }
            for ep in (data.get("episodes") or [])
        ],
    }


def bangumi_rank(c: Client, season_type: int = 1, day: int = 3, limit: int = 20) -> list[dict]:
    data = c.get(
        "/pgc/web/rank/list",
        {"season_type": season_type, "day": day},
        referer="https://www.bilibili.com/",
    )
    rows = data.get("list") or []
    def _score(value: Any) -> Any:
        return value.get("score", 0) if isinstance(value, dict) else (value or 0)

    return [
        {
            "season_id": r.get("season_id"),
            "title": r.get("title", ""),
            "score": _score(r.get("rating")),
            "badge": r.get("badge", ""),
            "cover": r.get("cover", ""),
        }
        for r in rows[:limit]
    ]


def article(c: Client, cvid: str) -> dict[str, Any]:
    data = c.get("/x/article/view", {"id": cvid})
    return {
        "id": data.get("id"),
        "title": data.get("title", ""),
        "summary": data.get("summary", ""),
        "banner": data.get("banner_url", ""),
        "author": {"id": data.get("mid"), "name": data.get("author_name", "")},
        "stats": {
            "view": _int((data.get("stats") or {}).get("view")),
            "like": _int((data.get("stats") or {}).get("like")),
            "reply": _int((data.get("stats") or {}).get("reply")),
        },
    }


def user_articles(c: Client, mid: str, page: int = 1, limit: int = 20) -> list[dict]:
    data = c.get(
        "/x/space/wbi/article",
        {"mid": mid, "pn": page, "ps": min(limit, 30)},
        wbi=True,
        referer=f"https://space.bilibili.com/{mid}/article",
    )
    rows = data.get("articles") or []
    return [
        {
            "id": r.get("id"),
            "title": (r.get("title") or "")[:80],
            "summary": (r.get("summary") or "")[:120],
            "view": _int((r.get("stats") or {}).get("view")),
            "publish_time": r.get("publish_time", 0),
        }
        for r in rows[:limit]
    ]


def collections(c: Client, mid: str, page: int = 1, limit: int = 10) -> list[dict]:
    """合集 / 系列列表（seasons_list 与 series_list）。"""
    data = c.get(
        "/x/polymer/web-space/seasons_series_list",
        {"mid": mid, "page_num": page, "page_size": limit},
        referer=f"https://space.bilibili.com/{mid}/",
    )
    lists = data.get("items_lists") or {}
    out: list[dict] = []
    for key, kind in (("seasons_list", "season"), ("series_list", "series")):
        for item in lists.get(key) or []:
            meta = item.get("meta") or {}
            out.append(
                {
                    "type": kind,
                    "id": meta.get("season_id") or meta.get("series_id"),
                    "title": meta.get("name", ""),
                    "cover": meta.get("cover", ""),
                    "total": _int(meta.get("total")),
                }
            )
    return out[:limit]


def timeline(c: Client, day: int = 3) -> list[dict]:
    """番剧更新表：types=1 番剧，day 为星期几（1-7）。"""
    data = c.get(
        "/pgc/web/timeline",
        {"types": 1, "before": 6, "after": 6},
        referer="https://www.bilibili.com/anime/timeline/",
    )
    rows = data if isinstance(data, list) else (data.get("list") or [])
    out: list[dict] = []
    for item in rows or []:
        for ep in item.get("episodes") or []:
            out.append(
                {
                    "season_id": ep.get("season_id"),
                    "title": ep.get("title", ""),
                    "pub_index": ep.get("pub_index", ""),
                    "pub_time": ep.get("pub_time", ""),
                    "day": day,
                }
            )
    return out
