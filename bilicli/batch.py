"""Batch resolution + download for videos, bangumi, favourites, collections."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import api, media
from .http import Client

BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
AV_RE = re.compile(r"av(\d+)", re.I)


def _kind_of(target: str) -> tuple[str, dict[str, str]]:
    query = parse_qs(urlparse(target).query)
    flat = {k: v[0] for k, v in query.items()}
    if "fid" in flat and "favlist" in target:
        return "fav", flat
    if "sid" in flat and ("lists" in target or "list" in target):
        return "list", flat
    if "/cheese/" in target:
        return "course", flat
    if "bangumi" in target or "ep_id" in flat or "season_id" in flat or re.fullmatch(r"(ep|ss|md)\d+", target):
        return "bangumi", flat
    if "/video" in target or BV_RE.search(target) or AV_RE.search(target):
        return "video", flat
    if "space.bilibili.com" in target:
        return "space", flat
    return "video", flat


def _space_mid(target: str, params: dict[str, str]) -> str:
    match = re.search(r"space\.bilibili\.com/(\d+)", target)
    if match:
        return match.group(1)
    return params.get("mid", "")


def resolve(c: Client, target: str, limit: int = 0) -> dict[str, Any]:
    kind, params = _kind_of(target)
    items: list[dict[str, Any]] = []
    title = ""

    if kind == "video":
        bvid = api.bvid_of(target)
        info = c.get("/x/web-interface/view", {"bvid": bvid})
        items = [{"bvid": bvid, "title": info.get("title", bvid)}]
        title = info.get("title", bvid)

    elif kind == "bangumi":
        season_id = params.get("season_id", "")
        ep_id = params.get("ep_id", "")
        if not season_id and not ep_id:
            num = re.sub(r"\D", "", target)
            if target.startswith("ep"):
                ep_id = num
            else:
                season_id = num
        data = c.get(
            "/pgc/view/web/season",
            {"season_id": season_id} if season_id else {"ep_id": ep_id},
            referer="https://www.bilibili.com/bangumi/",
        )
        title = data.get("title", "")
        for ep in data.get("episodes") or []:
            if ep.get("bvid"):
                items.append({"bvid": ep["bvid"], "title": f"{ep.get('title','')} {ep.get('long_title','')}".strip()})

    elif kind == "course":
        ep_id = re.sub(r"\D", "", target)
        data = c.get("/pugv/view/web/season", {"ep_id": ep_id}, referer="https://www.bilibili.com/cheese/")
        title = data.get("title", "")
        for ep in data.get("episodes") or []:
            if ep.get("bvid"):
                items.append({"bvid": ep["bvid"], "title": ep.get("title", "")})

    elif kind == "fav":
        media_id = params.get("fid", "")
        data = c.get("/x/v3/fav/resource/list", {"media_id": media_id, "pn": 1, "ps": 40}, auth_required=True)
        title = (data.get("info") or {}).get("title", f"fav {media_id}")
        items = [{"bvid": m.get("bvid"), "title": m.get("title", "")} for m in (data.get("medias") or []) if m.get("bvid")]

    elif kind == "list":
        mid = params.get("mid") or _space_mid(target, params)
        season_id = params.get("sid", "")
        data = c.get(
            "/x/polymer/web-space/seasons_archives_list",
            {"mid": mid, "season_id": season_id, "page_num": 1, "page_size": 30},
            referer=f"https://space.bilibili.com/{mid}/",
        )
        title = f"season {season_id}"
        items = [{"bvid": a.get("bvid"), "title": a.get("title", "")} for a in (data.get("archives") or []) if a.get("bvid")]

    elif kind == "space":
        mid = _space_mid(target, params)
        rows = api.user_videos(c, mid, 1, 50)
        title = f"UP {mid}"
        items = [{"bvid": r["bvid"], "title": r["title"]} for r in rows]

    if limit > 0:
        items = items[:limit]
    return {"kind": kind, "title": title, "count": len(items), "items": items}


def download_all(c: Client, items: list[dict], out_dir: Path, quality: int = 80) -> dict[str, Any]:
    results = []
    for index, item in enumerate(items, 1):
        try:
            result = media.download_video(c, item["bvid"], out_dir, quality)
            results.append({"index": index, "bvid": item["bvid"], "ok": True, "file": result["file"]})
        except Exception as exc:  # noqa: BLE001 - keep the batch going
            results.append({"index": index, "bvid": item["bvid"], "ok": False, "error": str(exc)})
    done = sum(1 for r in results if r["ok"])
    return {"total": len(items), "downloaded": done, "failed": len(items) - done, "results": results}
