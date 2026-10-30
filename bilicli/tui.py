"""Minimal REPL/TUI: list something, then act on the rows by index."""

from __future__ import annotations

import shutil
import sys
from typing import Any

from . import api, auth, format
from .http import ApiError, AuthError, NetworkError


def _header(text: str) -> None:
    width = shutil.get_terminal_size((100, 20)).columns
    print(f"\n\033[1m{text}\033[0m".center(width))


def _rows(items: list[dict], cols: list[str]) -> None:
    if not items:
        print("（空）")
        return
    short = [{c: (str(r.get(c, ""))[:60]) for c in cols} for r in items]
    print(format.table(short), end="")


HELP = """命令：
  hot / rank             热门 / 排行
  search <关键词>         搜索视频
  user <uid>             看 UP 主投稿
  open <序号>             看视频详情
  dl <序号>               下载视频到当前目录
  back                   返回上一层
  q / quit               退出
"""


def run() -> int:
    c = auth.client()
    stack: list[tuple[str, list[dict]]] = []
    current: list[dict] = []
    title = "bili"

    print("bili TUI — 输入 help 看命令，q 退出")
    if not c.logged_in:
        print("（未登录，只读命令可用）")

    while True:
        try:
            line = input(f"\n[{title}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        parts = line.split(maxsplit=1)
        cmd, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else "")

        try:
            if cmd in {"q", "quit", "exit"}:
                return 0
            if cmd in {"help", "?"}:
                print(HELP)
                continue
            if cmd == "back":
                if stack:
                    title, current = stack.pop()
                    _header(title)
                    _rows(current, ["title", "bvid", "author", "play", "duration"])
                continue
            if cmd in {"hot", "rank"}:
                stack.append((title, current))
                current = api.hot(c, 20) if cmd == "hot" else api.rank(c, 20)
                title = "热门" if cmd == "hot" else "排行"
                _header(title)
                _rows(current, ["title", "bvid", "owner", "view", "duration"])
                continue
            if cmd == "search":
                if not arg:
                    print("用法：search <关键词>")
                    continue
                stack.append((title, current))
                current = api.search(c, arg, "video", 1, 20)
                title = f"搜索：{arg}"
                _header(title)
                _rows(current, ["title", "bvid", "author", "play", "duration"])
                continue
            if cmd == "user":
                if not arg:
                    print("用法：user <uid>")
                    continue
                stack.append((title, current))
                current = api.user_videos(c, arg, 1, 20)
                title = f"UP {arg}"
                _header(title)
                _rows(current, ["title", "bvid", "play", "duration"])
                continue
            if cmd in {"open", "dl"}:
                if not arg.isdigit() or not (1 <= int(arg) <= len(current)):
                    print("序号无效")
                    continue
                item = current[int(arg) - 1]
                bvid = item.get("bvid")
                if not bvid:
                    print("这一行没有 BV 号")
                    continue
                if cmd == "open":
                    data = api.video(c, bvid, comments=True)
                    print(f"\n{data['title']}\n{data['url']}")
                    print((data.get("description") or "")[:300])
                    for cm in (data.get("comments") or [])[:5]:
                        print(f"  · {cm['author']}: {cm['message'][:80]}")
                else:
                    from pathlib import Path

                    from . import media

                    result = media.download_video(c, bvid, Path.cwd(), 64)
                    print(f"已下载：{result['file']} ({result['bytes'] // 1024} KB)")
                continue
            print("未知命令，输入 help")
        except AuthError:
            print("需要登录：先运行 bili login")
        except (ApiError, NetworkError) as exc:
            print(f"错误：{exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"意外错误：{type(exc).__name__}: {exc}")
