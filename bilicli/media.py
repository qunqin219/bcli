"""Media: full video download, subtitle/danmaku export."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .http import Client, NetworkError, NotFoundError

QUALITY_NAMES = {
    127: "8K",
    126: "杜比视界",
    125: "HDR",
    120: "4K",
    116: "1080P60",
    112: "1080P+",
    80: "1080P",
    74: "720P60",
    64: "720P",
    32: "480P",
    16: "360P",
}


def pick_stream(streams: list[dict], target: int) -> dict:
    """Closest stream at or below the requested quality id."""
    usable = [s for s in streams if s.get("id")]
    if not usable:
        raise NotFoundError("no_stream", "没有可用的视频流")
    below = [s for s in usable if s["id"] <= target]
    pool = below or usable
    return max(pool, key=lambda s: (s["id"], s.get("bandwidth", 0)))


def download_video(
    c: Client,
    bvid: str,
    out_dir: Path,
    quality: int = 80,
    part: int = 1,
    audio_only: bool = False,
) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    pages = info.get("pages") or []
    cid = info.get("cid")
    if part > 1:
        picked = next((p for p in pages if int(p.get("page", 0)) == part), None)
        if not picked:
            raise NotFoundError("no_part", f"没有第 {part} P")
        cid = picked.get("cid")
    play = c.get("/x/player/playurl", {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1})
    dash = play.get("dash") or {}
    videos = dash.get("video") or []
    audios = dash.get("audio") or []
    if not videos:
        raise NotFoundError("no_video", "该视频没有 DASH 流（可能是付费内容）")

    video = pick_stream(videos, quality)
    audio = max(audios, key=lambda a: a.get("bandwidth", 0)) if audios else None

    out_dir.mkdir(parents=True, exist_ok=True)
    if audio_only:
        if not audio:
            raise NotFoundError("no_audio", "没有音轨")
        safe = "".join(ch for ch in info.get("title", bvid) if ch not in '<>:"/\\|?*')[:100] or bvid
        target = out_dir / f"{safe}.m4a"
        c.download(audio.get("baseUrl") or audio.get("base_url"), str(target))
        return {"bvid": bvid, "title": info.get("title"), "file": str(target), "bytes": target.stat().st_size, "audio_only": True}
    vpath = out_dir / "_video.m4s"
    apath = out_dir / "_audio.m4s"
    c.download(video.get("baseUrl") or video.get("base_url"), str(vpath))
    if audio:
        c.download(audio.get("baseUrl") or audio.get("base_url"), str(apath))

    safe = "".join(ch for ch in info.get("title", bvid) if ch not in '<>:"/\\|?*')[:100] or bvid
    final = out_dir / f"{safe}.mp4"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg 未安装，无法合并音视频")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(vpath)]
    if audio:
        cmd += ["-i", str(apath)]
    cmd += ["-c", "copy", str(final)]
    subprocess.run(cmd, check=True)
    vpath.unlink(missing_ok=True)
    apath.unlink(missing_ok=True)

    return {
        "bvid": bvid,
        "title": info.get("title"),
        "quality": QUALITY_NAMES.get(video.get("id"), str(video.get("id"))),
        "file": str(final),
        "bytes": final.stat().st_size,
    }


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def subtitle_srt(c: Client, bvid: str, out: Path | None = None, lang: str = "") -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    player = c.get("/x/player/wbi/v2", {"bvid": bvid, "cid": info.get("cid")}, wbi=True)
    tracks = (player.get("subtitle") or {}).get("subtitles") or []
    if not tracks:
        raise NotFoundError("no_subtitle", "该视频没有字幕")
    track = next((t for t in tracks if lang and t.get("lan") == lang), tracks[0])
    url = track.get("subtitle_url") or ""
    if url.startswith("//"):
        url = "https:" + url
    import json
    import urllib.request

    from .http import UA

    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read())

    lines = []
    for idx, seg in enumerate(body.get("body") or [], 1):
        start = float(seg.get("from", 0))
        end = float(seg.get("to", start + 1))
        lines.append(f"{idx}\n{_srt_time(start)} --> {_srt_time(end)}\n{seg.get('content', '')}\n")
    srt = "\n".join(lines)

    result: dict[str, Any] = {"bvid": bvid, "lan": track.get("lan"), "lan_doc": track.get("lan_doc"), "cues": len(lines)}
    if out:
        out.write_text(srt, encoding="utf-8")
        result["file"] = str(out)
    else:
        result["srt"] = srt
    return result


def danmaku_export(c: Client, bvid: str, fmt: str = "txt", limit: int = 5000) -> dict[str, Any]:
    import xml.etree.ElementTree as ET

    info = c.get("/x/web-interface/view", {"bvid": bvid})
    raw = c._open(f"https://api.bilibili.com/x/v1/dm/list.so?oid={info.get('cid')}", c.headers())
    root = ET.fromstring(raw.decode("utf-8", "ignore"))
    items = root.findall("d")[:limit]
    if fmt == "xml":
        body = raw.decode("utf-8", "ignore")
    else:
        body = "\n".join(
            f"{float((d.get('p') or '0,0').split(',')[0]):.1f}\t{d.text or ''}" for d in items
        )
    return {"bvid": bvid, "count": len(items), "format": fmt, "content": body}
