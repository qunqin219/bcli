"""Bilibili endpoints and payload normalisation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .http import API, Client, NotFoundError

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


def search(c: Client, keyword: str, kind: str = "video", page: int = 1, limit: int = 20) -> list[dict]:
    payload = c.get(
        "/x/web-interface/wbi/search/type",
        {
            "search_type": kind,
            "keyword": keyword,
            "page": page,
            "page_size": min(max(limit, 1), 50),
        },
        wbi=True,
    )
    if kind == "video":
        rows = payload.get("result") or []
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
    rows = payload.get("result") or []
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


def user_videos(c: Client, uid: str, page: int = 1, limit: int = 20) -> list[dict]:
    payload = c.get(
        "/x/space/wbi/arc/search",
        {"mid": uid, "pn": page, "ps": min(limit, 50), "order": "pubdate"},
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


def rank(c: Client, limit: int = 20) -> list[dict]:
    rows = (c.get("/x/web-interface/ranking/v2", {"rid": 0, "type": "all"}) or {}).get("list") or []
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


def dynamic_feed(c: Client, limit: int = 20) -> list[dict]:
    payload = c.get("/x/polymer/web-dynamic/v1/feed/all", {"type": "all", "page": 1}, auth_required=True)
    return [_dynamic_item(i) for i in (payload.get("items") or [])[:limit]]


def my_dynamics(c: Client, limit: int = 20) -> list[dict]:
    me = whoami(c)
    payload = c.get(
        "/x/polymer/web-dynamic/v1/feed/space",
        {"host_mid": me["id"], "timezone_offset": -480},
        auth_required=True,
    )
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

    python = os.environ.get("BCLI_ASR_PYTHON", "/root/venvs/sensevoice/bin/python")
    worker = Path(os.environ.get("BCLI_ASR_WORKER", Path(__file__).resolve().parent.parent / "scripts" / "asr_worker.py"))
    if not Path(python).exists():
        raise FileNotFoundError(f"ASR 环境不存在: {python}（设置 BCLI_ASR_PYTHON）")
    if not worker.exists():
        raise FileNotFoundError(f"ASR worker 不存在: {worker}")

    env = dict(os.environ)
    if model:
        env["BCLI_ASR_MODEL"] = model
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


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")
