"""Command line interface for bcli."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__
from . import api, auth
from .http import ApiError, AuthError, NetworkError, NotFoundError

EXIT_OK = 0
EXIT_API = 1
EXIT_AUTH = 2
EXIT_NETWORK = 3


class Envelope:
    @staticmethod
    def ok(data: Any) -> dict[str, Any]:
        return {"ok": True, "schema_version": SCHEMA_VERSION, "data": data}

    @staticmethod
    def err(code: str, message: str, detail: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if detail is not None:
            error["detail"] = detail
        return {"ok": False, "schema_version": SCHEMA_VERSION, "error": error}


def emit(payload: dict[str, Any], pretty: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bcli", description="bcli — 零依赖的 B 站命令行工具")
    p.add_argument("--version", action="version", version=f"bcli {__version__}")
    p.add_argument("--pretty", action="store_true", help="缩进输出 JSON")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="登录状态")
    sub.add_parser("whoami", help="当前账号信息")

    login = sub.add_parser("login", help="扫码登录")
    login.add_argument("--png", type=Path, default=None, help="把二维码另存为 PNG")
    login.add_argument("--timeout", type=int, default=280)

    sub.add_parser("logout", help="清除本地凭证")

    s = sub.add_parser("search", help="搜索视频或用户")
    s.add_argument("keyword")
    s.add_argument("--type", choices=["video", "user"], default="video")
    s.add_argument("-n", "--limit", type=int, default=20)
    s.add_argument("--page", type=int, default=1)

    v = sub.add_parser("video", help="视频详情")
    v.add_argument("bvid")
    v.add_argument("-s", "--subtitle", action="store_true")
    v.add_argument("-c", "--comments", action="store_true")

    u = sub.add_parser("user", help="UP 主资料")
    u.add_argument("uid")

    uv = sub.add_parser("user-videos", help="UP 主投稿")
    uv.add_argument("uid")
    uv.add_argument("-n", "--limit", type=int, default=20)
    uv.add_argument("--page", type=int, default=1)

    sub.add_parser("hot", help="热门")
    sub.add_parser("rank", help="排行榜")
    sub.add_parser("history", help="观看历史")
    sub.add_parser("favorites", help="收藏夹列表")
    sub.add_parser("watch-later", help="稍后再看")
    sub.add_parser("feed", help="关注动态")
    sub.add_parser("my-dynamics", help="我的动态")

    a = sub.add_parser("audio", help="下载音频（可选切分为 16k WAV）")
    a.add_argument("bvid")
    a.add_argument("-o", "--output", type=Path, default=Path("."))
    a.add_argument("--segment", type=int, default=25)
    a.add_argument("--no-split", action="store_true")

    s_asr = sub.add_parser("asr", help="音频转文字（SenseVoice）")
    s_asr.add_argument("target", help="BV 号 / 视频 URL / 本地音频文件")
    s_asr.add_argument("-o", "--output", type=Path, default=None, help="音频与转写输出的目录")
    s_asr.add_argument("--segment", type=int, default=300)
    s_asr.add_argument("--model", default=None, help="SenseVoice 模型目录")
    s_asr.add_argument("--keep-audio", action="store_true", help="保留切分后的 WAV")

    r = sub.add_parser("api", help="原始 API 调用（调试用）")
    r.add_argument("path")
    r.add_argument("--param", action="append", default=[], metavar="K=V")
    r.add_argument("--wbi", action="store_true")

    return p


def run(args: argparse.Namespace) -> Any:
    cmd = args.command
    if cmd == "status":
        cred = auth.load_credential()
        c = auth.client()
        info = None
        if c.logged_in:
            try:
                info = api.whoami(c)
            except (ApiError, NetworkError):
                info = None
        return {
            "authenticated": info is not None,
            "credential_file": str(auth.CREDENTIAL_FILE),
            "has_sessdata": bool(cred.get("sessdata")),
            "user": info,
        }
    if cmd == "whoami":
        return api.whoami(auth.client())
    if cmd == "login":
        def state(s: str) -> None:
            print(f"[login] {s}", file=sys.stderr, flush=True)

        cred = auth.qr_login(png=args.png, timeout=args.timeout, on_state=state)
        return {"logged_in": True, "uid": cred.get("dedeuserid", "")}
    if cmd == "logout":
        auth.clear_credential()
        return {"logged_out": True}
    if cmd == "search":
        return api.search(auth.client(), args.keyword, args.type, args.page, args.limit)
    if cmd == "video":
        return api.video(auth.client(), api.bvid_of(args.bvid), args.subtitle, args.comments)
    if cmd == "user":
        return api.user(auth.client(), args.uid)
    if cmd == "user-videos":
        return api.user_videos(auth.client(), args.uid, args.page, args.limit)
    if cmd == "hot":
        return api.hot(auth.client())
    if cmd == "rank":
        return api.rank(auth.client())
    if cmd == "history":
        return api.history(auth.client())
    if cmd == "favorites":
        return api.favorites(auth.client())
    if cmd == "watch-later":
        return api.watch_later(auth.client())
    if cmd == "feed":
        return api.dynamic_feed(auth.client())
    if cmd == "my-dynamics":
        return api.my_dynamics(auth.client())
    if cmd == "audio":
        return api.audio(
            auth.client(),
            api.bvid_of(args.bvid),
            args.output,
            segment=args.segment,
            split=not args.no_split,
        )
    if cmd == "asr":
        target: str = args.target
        if api.BVID_RE.search(target):
            out_dir = args.output or Path(tempfile.gettempdir()) / "bcli-asr" / api.bvid_of(target)
            audio_result = api.audio(
                auth.client(), api.bvid_of(target), out_dir,
                segment=args.segment, split=True,
            )
            paths = audio_result["segments"]
            meta: dict[str, Any] = audio_result
        else:
            paths = [target]
            meta = {"file": target}
        result = api.transcribe(paths, model=args.model)
        if not args.keep_audio and api.BVID_RE.search(target):
            for p in paths:
                Path(p).unlink(missing_ok=True)
        return {"source": meta, "transcription": result}
    if cmd == "api":
        params = {}
        for item in args.param:
            k, _, val = item.partition("=")
            params[k] = val
        return auth.client().get(args.path, params, wbi=args.wbi)
    raise SystemExit(f"unknown command: {cmd}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        emit(Envelope.ok(run(args)), pretty=args.pretty)
        return EXIT_OK
    except AuthError as exc:
        emit(Envelope.err("not_authenticated", str(exc)), pretty=args.pretty)
        return EXIT_AUTH
    except NotFoundError as exc:
        emit(Envelope.err("not_found", str(exc)), pretty=args.pretty)
        return EXIT_API
    except ApiError as exc:
        emit(Envelope.err("api_error", str(exc), {"code": exc.code}), pretty=args.pretty)
        return EXIT_API
    except NetworkError as exc:
        emit(Envelope.err("network_error", str(exc)), pretty=args.pretty)
        return EXIT_NETWORK
    except ValueError as exc:
        emit(Envelope.err("invalid_argument", str(exc)), pretty=args.pretty)
        return EXIT_API
    except FileNotFoundError as exc:
        emit(Envelope.err("missing_dependency", str(exc)), pretty=args.pretty)
        return EXIT_API
    except RuntimeError as exc:
        emit(Envelope.err("runtime_error", str(exc)), pretty=args.pretty)
        return EXIT_API


if __name__ == "__main__":
    sys.exit(main())
