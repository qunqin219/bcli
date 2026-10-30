"""Bilibili endpoints and payload normalisation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .http import API, Client, NetworkError, NotFoundError

BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")


def bvid_of(value: str) -> str:
    match = BVID_RE.search(value)
    if not match:
        raise ValueError(f"无法识别 BV 号: {value}")
    return match.group(0)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stat(value: Any) -> int:
    if isinstance(value, dict):
        return _int(value.get("value") or value.get("count"))
    return _int(value)


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
def whoami(c: Client) -> dict[str, Any]:
    nav = c.get("/x/web-interface/nav", auth_required=True)
    if not nav.get("isLogin"):
        raise NotFoundError("not_logged_in", "登录态已失效，请重新扫码")
    return {
        "id": str(nav.get("mid", "")),
        "name": nav.get("uname", ""),
        "level": nav.get("level_info", {}).get("current_level", 0),
        "coins": nav.get("money", 0),
        "vip": (nav.get("vipStatus") == 1),
    }


def search(
    c: Client,
    keyword: str,
    kind: str = "video",
    page: int = 1,
    limit: int = 20,
    order: str = "totalrank",
    duration: int = 0,
    tids: int = 0,
) -> list[dict]:
    params: dict[str, Any] = {
        "search_type": kind,
        "keyword": keyword,
        "page": page,
        "page_size": min(max(limit, 1), 50),
    }
    if kind == "video":
        params.update({"order": order, "duration": duration, "tids": tids})
    payload = c.get("/x/web-interface/wbi/search/type", params, wbi=True)
    rows = payload.get("result") or []
    if not isinstance(rows, list):
        rows = (rows or {}).get("list") if isinstance(rows, dict) else []
    rows = rows or []
    if kind == "video":
        return [
            {
                "bvid": r.get("bvid"),
                "title": _clean(r.get("title", "")),
                "author": _clean(r.get("author", "")),
                "play": _int(r.get("play")),
                "duration": r.get("duration", ""),
                "url": f"https://www.bilibili.com/video/{r.get('bvid')}",
            }
            for r in rows[:limit]
        ]
    if kind == "article":
        return [
            {"id": r.get("id"), "title": _clean(r.get("title", "")), "author": r.get("author", ""),
             "view": _int(r.get("view")), "url": f"https://www.bilibili.com/read/cv{r.get('id')}"}
            for r in rows[:limit]
        ]
    if kind == "bangumi":
        return [
            {"season_id": r.get("season_id"), "title": _clean(r.get("title", "")), "type": r.get("season_type_name", "")}
            for r in rows[:limit]
        ]
    return [
        {
            "uid": str(r.get("mid", "")),
            "name": _clean(r.get("uname", "")),
            "sign": _clean(r.get("usign", "")),
            "fans": _int(r.get("fans")),
            "videos": _int(r.get("videos")),
        }
        for r in rows[:limit]
    ]


def video(c: Client, bvid: str, subtitles: bool = False, comments: bool = False) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    out: dict[str, Any] = {
        "bvid": info.get("bvid"),
        "aid": info.get("aid"),
        "cid": info.get("cid"),
        "title": info.get("title"),
        "description": info.get("desc", ""),
        "duration": info.get("duration", 0),
        "url": f"https://www.bilibili.com/video/{info.get('bvid')}",
        "owner": {
            "id": str(info.get("owner", {}).get("mid", "")),
            "name": info.get("owner", {}).get("name", ""),
        },
        "stats": {
            "view": _int(info.get("stat", {}).get("view")),
            "like": _int(info.get("stat", {}).get("like")),
            "coin": _int(info.get("stat", {}).get("coin")),
            "favorite": _int(info.get("stat", {}).get("favorite")),
            "reply": _int(info.get("stat", {}).get("reply")),
            "danmaku": _int(info.get("stat", {}).get("danmaku")),
        },
    }
    if subtitles:
        out["subtitle"] = _subtitles(c, bvid, str(info.get("cid")))
    if comments:
        out["comments"] = _comments(c, str(info.get("aid")))
    return out


def _subtitles(c: Client, bvid: str, cid: str) -> dict[str, Any]:
    player = c.get("/x/player/wbi/v2", {"bvid": bvid, "cid": cid}, wbi=True)
    tracks = (player.get("subtitle") or {}).get("subtitles") or []
    if not tracks:
        return {"available": False, "tracks": [], "text": ""}
    track = tracks[0]
    url = track.get("subtitle_url") or ""
    if url.startswith("//"):
        url = "https:" + url
    body = _raw_json(url)
    lines = [seg.get("content", "") for seg in (body.get("body") or [])]
    return {
        "available": True,
        "lan": track.get("lan", ""),
        "lan_doc": track.get("lan_doc", ""),
        "tracks": [{"lan": t.get("lan"), "lan_doc": t.get("lan_doc")} for t in tracks],
        "text": "\n".join(lines),
    }


def _raw_json(url: str) -> dict[str, Any]:
    import json
    import urllib.request

    from .http import UA

    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _comments(c: Client, aid: str, limit: int = 20) -> list[dict]:
    payload = c.get(
        "/x/v2/reply/wbi/main",
        {"oid": aid, "type": 1, "mode": 3, "ps": min(limit, 49), "next": 0},
        wbi=True,
    )
    replies = (payload.get("replies") or [])[:limit]
    return [
        {
            "id": str(r.get("rpid_str") or r.get("rpid") or ""),
            "author": r.get("member", {}).get("uname", ""),
            "message": (r.get("content") or {}).get("message", ""),
            "like": _int(r.get("like")),
            "replies": _int(r.get("rcount")),
        }
        for r in replies
    ]


def user(c: Client, uid: str) -> dict[str, Any]:
    data = c.get("/x/space/wbi/acc/info", {"mid": uid}, wbi=True)
    stat = c.get("/x/relation/stat", {"vmid": uid})
    return {
        "uid": str(data.get("mid", uid)),
        "name": data.get("name", ""),
        "sign": data.get("sign", ""),
        "level": data.get("level", 0),
        "fans": _int(stat.get("follower")),
        "following": _int(stat.get("following")),
    }


def user_videos(c: Client, uid: str, page: int = 1, limit: int = 20, order: str = "pubdate") -> list[dict]:
    payload = c.get(
        "/x/space/wbi/arc/search",
        {"mid": uid, "pn": page, "ps": min(limit, 50), "order": order},
        wbi=True,
        referer=f"https://space.bilibili.com/{uid}/video",
    )
    rows = ((payload.get("list") or {}).get("vlist")) or []
    return [
        {
            "bvid": r.get("bvid"),
            "title": _clean(r.get("title", "")),
            "play": _int(r.get("play")),
            "created": r.get("created"),
            "duration": r.get("length", ""),
        }
        for r in rows[:limit]
    ]


def hot(c: Client, limit: int = 20) -> list[dict]:
    rows = (c.get("/x/web-interface/popular", {"ps": min(limit, 50), "pn": 1}) or {}).get("list") or []
    return [
        {
            "bvid": r.get("bvid"),
            "title": r.get("title"),
            "owner": (r.get("owner") or {}).get("name", ""),
            "view": _int((r.get("stat") or {}).get("view")),
            "duration": r.get("duration"),
        }
        for r in rows[:limit]
    ]


def rank(c: Client, limit: int = 20, rid: int = 0) -> list[dict]:
    rows = (c.get("/x/web-interface/ranking/v2", {"rid": rid, "type": "all"}) or {}).get("list") or []
    return [
        {
            "bvid": r.get("bvid"),
            "title": r.get("title"),
            "owner": (r.get("owner") or {}).get("name", ""),
            "score": _int(r.get("score")),
            "view": _int((r.get("stat") or {}).get("view")),
        }
        for r in rows[:limit]
    ]


def history(c: Client, limit: int = 30) -> list[dict]:
    payload = c.get("/x/web-interface/history/cursor", {"ps": min(limit, 50), "type": "archive"}, auth_required=True)
    rows = payload.get("list") or []
    return [
        {
            "title": r.get("title", ""),
            "author": r.get("author_name", ""),
            "bvid": ((r.get("history") or {}).get("bvid") or ""),
            "kid": str(((r.get("history") or {}).get("oid") or r.get("kid") or "")),
            "viewed_at": r.get("view_at", 0),
            "progress": r.get("progress", 0),
        }
        for r in rows[:limit]
    ]


def favorites(c: Client) -> list[dict]:
    me = whoami(c)
    payload = c.get("/x/v3/fav/folder/created/list-all", {"up_mid": me["id"]}, auth_required=True)
    folders = payload.get("list") or []
    return [
        {"id": str(f.get("id", "")), "title": f.get("title", ""), "count": _int(f.get("media_count"))}
        for f in folders
    ]


def watch_later(c: Client, limit: int = 30) -> list[dict]:
    rows = (c.get("/x/v2/history/toview", auth_required=True) or {}).get("list") or []
    return [
        {
            "bvid": r.get("bvid"),
            "title": r.get("title"),
            "duration": r.get("duration"),
            "progress": r.get("progress", 0),
        }
        for r in rows[:limit]
    ]


def dynamic_feed(c: Client, limit: int = 20, page: int = 1) -> list[dict]:
    payload = c.get("/x/polymer/web-dynamic/v1/feed/all", {"type": "all", "page": page}, auth_required=True)
    return [_dynamic_item(i) for i in (payload.get("items") or [])[:limit]]


def my_dynamics(c: Client, limit: int = 20, offset: str = "") -> list[dict]:
    me = whoami(c)
    params: dict[str, Any] = {"host_mid": me["id"], "timezone_offset": -480}
    if offset:
        params["offset"] = offset
    payload = c.get("/x/polymer/web-dynamic/v1/feed/space", params, auth_required=True)
    return [_dynamic_item(i) for i in (payload.get("items") or [])[:limit]]





def _dynamic_item(item: dict[str, Any]) -> dict[str, Any]:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    body = modules.get("module_dynamic") or {}
    desc = body.get("desc") or {}
    stat = (modules.get("module_stat") or {}).get("comment") or {}
    pub_ts = _int(author.get("pub_ts"))
    return {
        "id": str(item.get("id_str") or item.get("id") or ""),
        "author": author.get("name", ""),
        "published_at": datetime.fromtimestamp(pub_ts, timezone.utc).astimezone().isoformat() if pub_ts else "",
        "text": desc.get("text", ""),
        "type": item.get("type", ""),
        "comments": _int((stat or {}).get("count")),
    }


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------
def audio(c: Client, bvid: str, out_dir: Path, segment: int = 25, split: bool = True) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    title = _safe_name(info.get("title", bvid))
    cid = info.get("cid")

    play = c.get("/x/player/playurl", {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1})
    dash = (play.get("dash") or {}).get("audio") or []
    legacy = (play.get("durl") or [])
    if dash:
        url = dash[0].get("baseUrl") or dash[0].get("base_url")
    elif legacy:
        url = legacy[0].get("url")
    else:
        raise NotFoundError("no_audio", "该视频没有可用音轨（可能是会员/付费内容）")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "_raw.m4a"
    size = c.download(url, str(raw))
    result: dict[str, Any] = {"title": info.get("title"), "bvid": bvid, "downloaded_bytes": size}

    if not split:
        final = out_dir / f"{title}.m4a"
        raw.replace(final)
        result["file"] = str(final)
        return result

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("需要 ffmpeg 才能切分；可加 --no-split 直接保存 m4a")
    parts = []
    pattern = out_dir / "seg_%03d.wav"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(raw), "-ac", "1", "-ar", "16000", "-f", "segment",
            "-segment_time", str(segment), "-reset_timestamps", "1", str(pattern),
        ],
        check=True,
    )
    raw.unlink(missing_ok=True)
    parts = sorted(str(p) for p in out_dir.glob("seg_*.wav"))
    result["segments"] = parts
    result["segment_seconds"] = segment
    return result


def _safe_name(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", title).strip(". ")
    return cleaned[:120] or "audio"


# --------------------------------------------------------------------------
# ASR (SenseVoice via an external worker)
# --------------------------------------------------------------------------
def transcribe(paths: list[str], model: str | None = None, timeout: int = 1800) -> dict[str, Any]:
    """Run SenseVoice on audio files through scripts/asr_worker.py.

    The model needs torch/funasr, which this CLI deliberately does not depend
    on; the worker runs in its own interpreter.
    """
    import json
    import subprocess

    python = config.get("asr_python") or shutil.which("python3") or "python3"
    worker = Path(config.get("asr_worker") or Path(__file__).resolve().parent.parent / "scripts" / "asr_worker.py")
    if not Path(python).exists() and not shutil.which(str(python)):
        raise FileNotFoundError(f"ASR 解释器不可用: {python}（设置 asr_python 或 BCLI_ASR_PYTHON）")
    if not worker.exists():
        raise FileNotFoundError(f"ASR worker 不存在: {worker}")

    env = dict(os.environ)
    model = model or config.get("asr_model")
    if model:
        env["BCLI_ASR_MODEL"] = str(model)
    proc = subprocess.run(
        [python, str(worker), *paths],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-800:] or "ASR worker 失败")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if not payload.get("ok"):
        raise RuntimeError((payload.get("error") or {}).get("message", "ASR 失败"))
    return payload["data"]


# --------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------
def like(c: Client, bvid: str, undo: bool = False) -> dict[str, Any]:
    # B站用 like=2 表示取消点赞，0 会返回 -400
    c.post("/x/web-interface/archive/like", {"bvid": bvid, "like": 2 if undo else 1})
    return {"bvid": bvid, "liked": not undo}


def coin(c: Client, bvid: str, count: int = 1, also_like: bool = False) -> dict[str, Any]:
    if count not in (1, 2):
        raise ValueError("投币数只能是 1 或 2")
    data = c.post(
        "/x/web-interface/coin/add",
        {"bvid": bvid, "multiply": count, "select_like": 1 if also_like else 0},
    )
    return {"bvid": bvid, "coins": count, "liked": also_like, "multiply": _int(data.get("multiply"))}


def triple(c: Client, bvid: str) -> dict[str, Any]:
    """点赞 + 投币 + 收藏到默认收藏夹。"""
    like(c, bvid)
    coin(c, bvid, 1, also_like=False)
    aid = str(c.get("/x/web-interface/view", {"bvid": bvid}).get("aid"))
    folders = favorites(c)
    folder_id = str(folders[0]["id"]) if folders else None
    if folder_id:
        c.post("/x/v3/fav/resource/deal", {"rid": aid, "type": 2, "add_media_ids": folder_id})
    return {"bvid": bvid, "liked": True, "coins": 1, "favorited": bool(folder_id)}


def follow(c: Client, uid: str, undo: bool = False) -> dict[str, Any]:
    c.post("/x/relation/modify", {"fid": uid, "act": 2 if undo else 1, "re_src": 11})
    return {"uid": uid, "following": not undo}


def favorite_add(c: Client, bvid: str, folder_id: str) -> dict[str, Any]:
    aid = str(c.get("/x/web-interface/view", {"bvid": bvid}).get("aid"))
    c.post("/x/v3/fav/resource/deal", {"rid": aid, "type": 2, "add_media_ids": folder_id})
    return {"bvid": bvid, "folder": folder_id, "added": True}


def favorite_remove(c: Client, bvid: str, folder_id: str) -> dict[str, Any]:
    aid = str(c.get("/x/web-interface/view", {"bvid": bvid}).get("aid"))
    c.post("/x/v3/fav/resource/deal", {"rid": aid, "type": 2, "del_media_ids": folder_id})
    return {"bvid": bvid, "folder": folder_id, "removed": True}


def comment(c: Client, bvid: str, message: str) -> dict[str, Any]:
    aid = c.get("/x/web-interface/view", {"bvid": bvid}).get("aid")
    data = c.post("/x/v2/reply/add", {"oid": aid, "type": 1, "message": message, "plat": 1})
    return {"bvid": bvid, "rpid": str((data.get("rpid_str") or data.get("rpid") or ""))}


# --------------------------------------------------------------------------
# extras
# --------------------------------------------------------------------------
def favorites_contents(c: Client, folder_id: str, page: int = 1, limit: int = 20) -> list[dict]:
    payload = c.get(
        "/x/v3/fav/resource/list",
        {"media_id": folder_id, "pn": page, "ps": min(limit, 40), "platform": "web"},
        auth_required=True,
    )
    rows = payload.get("medias") or []
    return [
        {
            "bvid": r.get("bvid", ""),
            "title": r.get("title", ""),
            "upper": (r.get("upper") or {}).get("name", ""),
            "duration": r.get("duration"),
            "fav_time": r.get("fav_time", 0),
        }
        for r in rows[:limit]
    ]


def ai_summary(c: Client, bvid: str) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    data = c.get(
        "/x/web-interface/view/conclusion/get",
        {"bvid": bvid, "cid": info.get("cid"), "up_mid": (info.get("owner") or {}).get("mid")},
        wbi=True,
        referer=f"https://www.bilibili.com/video/{bvid}",
    )
    model = data.get("model_result") or {}
    return {
        "bvid": bvid,
        "summary": model.get("summary", ""),
        "outline": [
            {"title": o.get("title", ""), "points": o.get("part_outline") or []}
            for o in (model.get("outline") or [])
        ],
    }


def related(c: Client, bvid: str, limit: int = 10) -> list[dict]:
    rows = c.get("/x/web-interface/archive/related", {"bvid": bvid}) or []
    items = rows.get("list") if isinstance(rows, dict) else rows
    return [
        {
            "bvid": r.get("bvid"),
            "title": r.get("title"),
            "owner": (r.get("owner") or {}).get("name", ""),
            "view": _int((r.get("stat") or {}).get("view")),
        }
        for r in (items or [])[:limit]
    ]


def parts(c: Client, bvid: str) -> list[dict]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    return [
        {"cid": p.get("cid"), "page": p.get("page"), "part": p.get("part", ""), "duration": p.get("duration")}
        for p in (info.get("pages") or [])
    ]


def chapters(c: Client, bvid: str) -> list[dict]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    player = c.get("/x/player/wbi/v2", {"bvid": bvid, "cid": info.get("cid")}, wbi=True)
    points = player.get("view_points") or []
    return [
        {
            "from": p.get("from"),
            "to": p.get("to"),
            "content": p.get("content", ""),
            "img": p.get("img", ""),
        }
        for p in points
    ]


def danmaku(c: Client, bvid: str, limit: int = 200) -> list[dict]:
    """弹幕以 XML 返回，标准库解析。"""
    import xml.etree.ElementTree as ET

    info = c.get("/x/web-interface/view", {"bvid": bvid})
    cid = info.get("cid")
    raw = c._open(f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}", c.headers())
    try:
        root = ET.fromstring(raw.decode("utf-8", "ignore"))
    except ET.ParseError as exc:
        raise NetworkError("弹幕解析失败") from exc
    out = []
    for d in root.findall("d")[:limit]:
        attr = (d.get("p") or "").split(",")
        out.append(
            {
                "time": float(attr[0]) if attr and attr[0] else 0.0,
                "mode": int(attr[1]) if len(attr) > 1 else 0,
                "text": d.text or "",
            }
        )
    return out


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


# --------------------------------------------------------------------------
# more writes: dynamics, favorites management, watch later, history
# --------------------------------------------------------------------------
def dynamic_post(c: Client, text: str) -> dict[str, Any]:
    import json

    dyn_req = {
        "dyn_req": {
            "content": {"contents": [{"raw_text": text, "type": 1, "biz_id": ""}]},
            "scene": 1,
        }
    }
    data = c.post("/x/dynamic/feed/create/dyn", {"dyn_req": json.dumps(dyn_req, ensure_ascii=False)})
    return {"dynamic_id": str((data.get("dyn_id_str") or data.get("dyn_id") or ""))}


def dynamic_delete(c: Client, dynamic_id: str) -> dict[str, Any]:
    c.post("/x/dynamic/feed/operate/remove", {"dynamic_id": dynamic_id})
    return {"dynamic_id": dynamic_id, "deleted": True}


def favorite_create(c: Client, title: str, private: bool = False) -> dict[str, Any]:
    data = c.post("/x/v3/fav/folder/add", {"title": title, "privacy": 1 if private else 0})
    return {"id": str(data.get("id", "")), "title": title, "private": private}


def favorite_delete(c: Client, folder_id: str) -> dict[str, Any]:
    c.post("/x/v3/fav/folder/del", {"media_ids": folder_id})
    return {"id": folder_id, "deleted": True}


def favorite_rename(c: Client, folder_id: str, title: str, private: bool | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"media_id": folder_id, "title": title}
    if private is not None:
        payload["privacy"] = 1 if private else 0
    c.post("/x/v3/fav/folder/edit", payload)
    return {"id": folder_id, "title": title}


def watch_later_add(c: Client, bvid: str) -> dict[str, Any]:
    aid = c.get("/x/web-interface/view", {"bvid": bvid}).get("aid")
    c.post("/x/v2/history/toview/add", {"aid": aid})
    return {"bvid": bvid, "added": True}


def watch_later_remove(c: Client, bvid: str) -> dict[str, Any]:
    aid = c.get("/x/web-interface/view", {"bvid": bvid}).get("aid")
    c.post("/x/v2/history/toview/del", {"aid": aid})
    return {"bvid": bvid, "removed": True}


def history_delete(c: Client, kid: str) -> dict[str, Any]:
    c.post("/x/v2/history/delete", {"kid": kid})
    return {"kid": kid, "deleted": True}


def history_clear(c: Client) -> dict[str, Any]:
    c.post("/x/v2/history/clear", {})
    return {"cleared": True}


def video_qualities(c: Client, bvid: str) -> list[dict]:
    """可用的视频清晰度列表（需要登录才能拿到大会员档位）。"""
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    play = c.get("/x/player/playurl", {"bvid": bvid, "cid": info.get("cid"), "fnval": 16, "fourk": 1})
    rows = (play.get("dash") or {}).get("video") or []
    seen: dict[int, dict] = {}
    for r in rows:
        qid = r.get("id")
        if qid and qid not in seen:
            seen[qid] = {"id": qid, "codec": r.get("codecs", ""), "bandwidth": r.get("bandwidth", 0)}
    return sorted(seen.values(), key=lambda x: -x["id"])
