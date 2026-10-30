"""Danmaku XML -> ASS subtitle conversion."""

from __future__ import annotations

import time
from typing import Any

WIDTH, HEIGHT = 1920, 1080
FONT = "Microsoft YaHei"
DURATION = 8.0
FONT_SIZE = 48


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def _color(bgr: int) -> str:
    # ASS uses &HBBGGRR&, the API already gives BGR as an int
    return f"&H{bgr & 0xFFFFFF:06X}&"


def convert(xml_text: str, limit: int = 5000) -> str:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    rows = root.findall("d")[:limit]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,1,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines: list[str] = []
    for d in rows:
        attr = (d.get("p") or "").split(",")
        if len(attr) < 7:
            continue
        try:
            start = float(attr[0])
            mode = int(attr[1])
            color = int(attr[3])
            text = (d.text or "").replace("\n", " ").replace("{", "（").replace("}", "）")
        except (ValueError, IndexError):
            continue
        end = start + DURATION
        if mode in (4,):
            template = r"{\an2\pos(%d,%d)}" % (WIDTH // 2, HEIGHT - 80)
        elif mode in (5,):
            template = r"{\an8\pos(%d,%d)}" % (WIDTH // 2, 80)
        else:
            template = r"{\move(%d,%d,%d,%d)}" % (WIDTH, 120, -int(len(text) * FONT_SIZE), 120)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Danmaku,,0,0,0,,{{{_color(color)}}}{template}{text}"
        )

    return header + "\n".join(lines) + "\n"


def export(c: Any, bvid: str, limit: int = 5000) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid})
    raw = c._open(f"https://api.bilibili.com/x/v1/dm/list.so?oid={info.get('cid')}", c.headers())
    text = raw.decode("utf-8", "ignore")
    ass = convert(text, limit)
    return {"bvid": bvid, "count": ass.count("Dialogue:"), "ass": ass}
