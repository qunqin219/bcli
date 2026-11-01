"""Keyframe extraction: give a multimodal agent a way to "watch" a video.

The video is pulled at a low quality (480P by default), then ffmpeg collects
scene-change frames; those are merged with evenly spaced samples so the timeline
is covered even in long talking-head stretches. Output is JPEG files plus
timestamps, optionally base64 so an MCP client can hand the pixels straight to a
vision model.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import media
from .http import Client

PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def _ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise FileNotFoundError("ffmpeg 未安装，取帧需要 ffmpeg")
    return ff


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-500:] or "ffmpeg 失败")
    return proc.stderr


def _scene_frames(mp4: Path, out: Path, scene: float, width: int) -> list[tuple[float, Path]]:
    pattern = out / "scene_%04d.jpg"
    for old in out.glob("scene_*.jpg"):
        old.unlink()
    err = _run(
        [
            _ffmpeg(), "-hide_banner", "-i", str(mp4),
            "-vf", f"select='gt(scene,{scene})',scale={width}:-2,showinfo",
            "-fps_mode", "vfr", "-q:v", "3", str(pattern),
        ]
    )
    times = [float(x) for x in PTS_RE.findall(err)]
    files = sorted(out.glob("scene_*.jpg"))
    return list(zip(times, files))


def _uniform_frames(mp4: Path, out: Path, count: int, duration: float, width: int) -> list[tuple[float, Path]]:
    pattern = out / "even_%04d.jpg"
    for old in out.glob("even_*.jpg"):
        old.unlink()
    fps = max(count / max(duration, 1.0), 0.01)
    _run(
        [
            _ffmpeg(), "-hide_banner", "-i", str(mp4),
            "-vf", f"fps={fps:.6f},scale={width}:-2",
            "-frames:v", str(count), "-q:v", "3", str(pattern),
        ]
    )
    files = sorted(out.glob("even_*.jpg"))
    step = max(duration, 1.0) / max(len(files), 1)
    return [(round(i * step, 2), f) for i, f in enumerate(files)]


def _merge(candidates: list[tuple[float, Path]], duration: float, count: int) -> list[tuple[float, Path]]:
    """Spread `count` picks across the timeline, preferring scene-cut frames."""
    candidates = sorted(candidates, key=lambda x: x[0])
    deduped: list[tuple[float, Path]] = []
    for ts, path in candidates:
        if deduped and abs(deduped[-1][0] - ts) < 1.0:
            path.unlink(missing_ok=True)
            continue
        deduped.append((ts, path))
    if not deduped:
        return []
    picked: list[tuple[float, Path]] = []
    used: set[Path] = set()
    for i in range(count):
        target = duration * (i + 0.5) / count
        best = min(
            (c for c in deduped if c[1] not in used),
            key=lambda c: abs(c[0] - target),
            default=None,
        )
        if best is None:
            break
        picked.append(best)
        used.add(best[1])
    for _, path in deduped:
        if path not in used:
            path.unlink(missing_ok=True)
    return sorted(picked, key=lambda x: x[0])


def extract(
    c: Client,
    bvid: str,
    out_dir: Path,
    count: int = 12,
    width: int = 960,
    scene: float = 0.3,
    quality: int = 32,
    inline: bool = False,
    keep_video: bool = False,
) -> dict[str, Any]:
    if count < 1 or count > 60:
        raise ValueError("count 需要在 1–60 之间")
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = media.download_video(c, bvid, out_dir, quality=quality, with_audio=False)
    mp4 = Path(downloaded["file"])
    duration = float(downloaded.get("duration") or 0)

    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    for stale in frames_dir.glob("*.jpg"):
        stale.unlink()

    candidates = _scene_frames(mp4, frames_dir, scene, width)
    candidates += _uniform_frames(mp4, frames_dir, max(count, 8), duration, width)
    picked = _merge(candidates, duration, count)

    items = []
    for idx, (ts, path) in enumerate(picked):
        item: dict[str, Any] = {
            "index": idx,
            "timestamp": round(ts, 2),
            "clock": f"{int(ts) // 60:02d}:{int(ts) % 60:02d}",
            "path": str(path),
            "bytes": path.stat().st_size,
        }
        if inline:
            item["jpeg_base64"] = base64.b64encode(path.read_bytes()).decode()
        items.append(item)

    if not keep_video:
        mp4.unlink(missing_ok=True)

    return {
        "bvid": bvid,
        "title": downloaded.get("title"),
        "duration": duration,
        "quality": downloaded.get("quality"),
        "source": "scene+uniform",
        "count": len(items),
        "frames_dir": str(frames_dir),
        "frames": items,
    }
