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
    p = argparse.ArgumentParser(prog="bili", description="bili — 零依赖的 B 站命令行工具")
    p.add_argument("--version", action="version", version=f"bili {__version__}")
    p.add_argument("--pretty", action="store_true", help="缩进输出 JSON")
    p.add_argument("--yaml", action="store_true", help="以 YAML 输出")
    p.add_argument("--fields", default="", help="逗号分隔，只保留这些字段")
    p.add_argument("--table", action="store_true", help="以表格输出（适合人看）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="登录状态")
    sub.add_parser("doctor", help="环境自检")
    sub.add_parser("whoami", help="当前账号信息")

    login = sub.add_parser("login", help="扫码登录")
    login.add_argument("--png", type=Path, default=None, help="把二维码另存为 PNG")
    login.add_argument("--timeout", type=int, default=280)
    login.add_argument("--profile", default="", help="多账号：保存为 credential-<profile>.json")

    sub.add_parser("logout", help="清除本地凭证")

    s = sub.add_parser("search", help="搜索视频或用户")
    s.add_argument("keyword")
    s.add_argument("--type", choices=["video", "user", "article", "bangumi"], default="video")
    s.add_argument("-n", "--limit", type=int, default=20)
    s.add_argument("--page", type=int, default=1)
    s.add_argument("--order", default="totalrank",
                   choices=["totalrank", "click", "pubdate", "dm", "stow", "scores"])
    s.add_argument("--duration", type=int, default=0, choices=[0, 1, 2, 3, 4],
                   help="0 全部 1 <10min 2 10-30min 3 30-60min 4 >60min")
    s.add_argument("--tids", type=int, default=0, help="分区 id，0 为全部")

    v = sub.add_parser("video", help="视频详情")
    v.add_argument("bvid")
    v.add_argument("-s", "--subtitle", action="store_true")
    v.add_argument("-c", "--comments", action="store_true")
    v.add_argument("--ai", action="store_true", help="AI 总结")
    v.add_argument("--related", action="store_true", help="相关推荐")
    v.add_argument("--parts", action="store_true", help="分 P 列表")
    v.add_argument("--chapters", action="store_true", help="章节")
    v.add_argument("--danmaku", action="store_true", help="弹幕")

    u = sub.add_parser("user", help="UP 主资料")
    u.add_argument("uid")

    uv = sub.add_parser("user-videos", help="UP 主投稿")
    uv.add_argument("uid")
    uv.add_argument("-n", "--limit", type=int, default=20)
    uv.add_argument("--page", type=int, default=1)
    uv.add_argument("--order", default="pubdate", choices=["pubdate", "click", "stow"])

    ht = sub.add_parser("hot", help="热门")
    ht.add_argument("-n", "--limit", type=int, default=20)
    rc = sub.add_parser("rcmd", help="首页推荐")
    rc.add_argument("-n", "--limit", type=int, default=12)
    rc.add_argument("--fresh-type", type=int, default=3, help="1=刷新 3=首次加载")
    rc.add_argument("--fresh-idx", type=int, default=1, help="越大越往下翻")
    rk = sub.add_parser("rank", help="排行榜")
    rk.add_argument("--rid", type=int, default=0, help="分区 id，0 为全站")
    rk.add_argument("-n", "--limit", type=int, default=20)
    sub.add_parser("history", help="观看历史")
    sub.add_parser("favorites", help="收藏夹列表")
    sub.add_parser("watch-later", help="稍后再看")
    f = sub.add_parser("feed", help="关注动态")
    f.add_argument("--page", type=int, default=1)
    f.add_argument("-n", "--limit", type=int, default=20)

    md = sub.add_parser("my-dynamics", help="我的动态")
    md.add_argument("--offset", default="")
    md.add_argument("-n", "--limit", type=int, default=20)

    fav = sub.add_parser("favorites-items", help="收藏夹内容")
    fav.add_argument("folder_id")
    fav.add_argument("--page", type=int, default=1)
    fav.add_argument("-n", "--limit", type=int, default=20)

    lk = sub.add_parser("like", help="点赞 / 取消点赞")
    lk.add_argument("bvid")
    lk.add_argument("--undo", action="store_true")

    cn = sub.add_parser("coin", help="投币")
    cn.add_argument("bvid")
    cn.add_argument("-n", "--count", type=int, default=1, choices=[1, 2])
    cn.add_argument("--also-like", action="store_true")

    sub.add_parser("triple", help="一键三连").add_argument("bvid")

    fo = sub.add_parser("follow", help="关注 / 取关")
    fo.add_argument("uid")
    fo.add_argument("--undo", action="store_true")

    fa = sub.add_parser("fav-add", help="收藏到指定收藏夹")
    fa.add_argument("bvid")
    fa.add_argument("folder_id")

    fr = sub.add_parser("fav-remove", help="从收藏夹移除")
    fr.add_argument("bvid")
    fr.add_argument("folder_id")

    cm = sub.add_parser("comment", help="发表评论")
    cm.add_argument("bvid")
    cm.add_argument("message")

    a = sub.add_parser("audio", help="下载音频（可选切分为 16k WAV）")
    a.add_argument("bvid")
    a.add_argument("-o", "--output", type=Path, default=Path("."))
    a.add_argument("--segment", type=int, default=25)
    a.add_argument("--no-split", action="store_true")

    s_asr = sub.add_parser("asr", help="音频转文字（SenseVoice / Qwen3-ASR）")
    s_asr.add_argument("target", help="BV 号 / 视频 URL / 本地音频文件")
    s_asr.add_argument("-o", "--output", type=Path, default=None, help="音频与转写输出的目录")
    s_asr.add_argument("--segment", type=int, default=300)
    s_asr.add_argument("--engine", default=None,
                       help="ASR 引擎: sensevoice / qwen3-asr / auto（默认读配置，否则用可用引擎）")
    s_asr.add_argument("--model", default=None, help="覆盖模型目录")
    s_asr.add_argument("--keep-audio", action="store_true", help="保留切分后的 WAV")
    s_asr.add_argument("--srt", type=Path, default=None, help="同时导出 SRT（按分段时长估算时间轴）")

    sub.add_parser("asr-engines", help="列出可用的 ASR 引擎及其路径")

    dl = sub.add_parser("daily", help="每日经验任务：登录/观看/分享/投币")
    dl.add_argument("--coins", type=int, default=0, help="投几个币（会消耗硬币，最多 5 个）")
    dl.add_argument("--share", action="store_true", help="执行每日分享（会在账号上产生一次公开分享）")
    dl.add_argument("--no-watch", action="store_true", help="跳过观看")
    dl.add_argument("--bvid", default=None, help="指定用于观看/分享的视频")
    dl.add_argument("--jitter", type=int, default=0, help="开始前随机等待 0..N 秒；动作之间另有随机间隔")

    fr = sub.add_parser("frames", help="抽取视频关键帧（给多模态 agent 看画面）")
    fr.add_argument("target", help="BV 号 / 视频 URL")
    fr.add_argument("-n", "--count", type=int, default=12, help="帧数，1–60")
    fr.add_argument("-o", "--output", type=Path, default=None, help="输出目录")
    fr.add_argument("--width", type=int, default=960, help="帧宽（像素）")
    fr.add_argument("--scene", type=float, default=0.3, help="场景变化阈值，越小取帧越密")
    fr.add_argument("--quality", type=int, default=32, help="下载画质 id（32=480P，16=360P）")
    fr.add_argument("--inline", action="store_true", help="在 JSON 里内嵌 base64，供 MCP/视觉模型直接使用")
    fr.add_argument("--keep-video", action="store_true", help="保留下载的 mp4")

    bg = sub.add_parser("bangumi", help="番剧/影视信息")
    bg.add_argument("season_id")
    bg.add_argument("--ep", action="store_true", help="把参数当作 ep_id")

    bgr = sub.add_parser("bangumi-rank", help="番剧排行")
    bgr.add_argument("--season-type", type=int, default=1)
    bgr.add_argument("--day", type=int, default=3)
    bgr.add_argument("-n", "--limit", type=int, default=20)

    ar = sub.add_parser("article", help="专栏文章")
    ar.add_argument("cvid")

    ua = sub.add_parser("user-articles", help="UP 主专栏")
    ua.add_argument("mid")
    ua.add_argument("--page", type=int, default=1)
    ua.add_argument("-n", "--limit", type=int, default=20)

    cl = sub.add_parser("collections", help="合集 / 系列")
    cl.add_argument("mid")
    cl.add_argument("--page", type=int, default=1)
    cl.add_argument("-n", "--limit", type=int, default=10)

    nt = sub.add_parser("notifications", help="消息中心")
    nt.add_argument("--kind", choices=["reply", "at", "like"], default="reply")
    nt.add_argument("--page", type=int, default=1)
    nt.add_argument("-n", "--limit", type=int, default=20)

    sub.add_parser("unread", help="未读消息数")

    fw = sub.add_parser("followings", help="关注列表")
    fw.add_argument("uid")
    fw.add_argument("--page", type=int, default=1)
    fw.add_argument("-n", "--limit", type=int, default=20)

    fn = sub.add_parser("fans", help="粉丝列表")
    fn.add_argument("uid")
    fn.add_argument("--page", type=int, default=1)
    fn.add_argument("-n", "--limit", type=int, default=20)

    cm = sub.add_parser("comments", help="视频评论（可翻页）")
    cm.add_argument("bvid")
    cm.add_argument("--cursor", default="")
    cm.add_argument("-n", "--limit", type=int, default=20)

    rp = sub.add_parser("reply", help="回复评论 / 发评论")
    rp.add_argument("bvid")
    rp.add_argument("message")
    rp.add_argument("--root", default="")
    rp.add_argument("--parent", default="")

    lc = sub.add_parser("like-comment", help="给评论点赞")
    lc.add_argument("bvid")
    lc.add_argument("rpid")
    lc.add_argument("--undo", action="store_true")

    dl = sub.add_parser("download", help="下载视频（DASH 合并为 mp4）")
    dl.add_argument("bvid")
    dl.add_argument("-o", "--output", type=Path, default=Path("."))
    dl.add_argument("--quality", type=int, default=80, help="80=1080P 64=720P 32=480P 16=360P")
    dl.add_argument("--part", type=int, default=1, help="第几 P")
    dl.add_argument("--audio-only", action="store_true", help="只下音轨")

    ss = sub.add_parser("subtitle-srt", help="导出字幕为 SRT")
    ss.add_argument("bvid")
    ss.add_argument("-o", "--output", type=Path, default=None)
    ss.add_argument("--lang", default="")

    de = sub.add_parser("danmaku-export", help="导出弹幕")
    de.add_argument("bvid")
    de.add_argument("--format", choices=["txt", "xml", "ass"], default="txt")
    de.add_argument("-n", "--limit", type=int, default=5000)

    dp = sub.add_parser("dynamic-post", help="发一条纯文本动态")
    dp.add_argument("text")

    dd = sub.add_parser("dynamic-delete", help="删除动态")
    dd.add_argument("dynamic_id")

    fc = sub.add_parser("fav-create", help="新建收藏夹")
    fc.add_argument("title")
    fc.add_argument("--private", action="store_true")

    fd = sub.add_parser("fav-delete", help="删除收藏夹")
    fd.add_argument("folder_id")

    frn = sub.add_parser("fav-rename", help="重命名收藏夹")
    frn.add_argument("folder_id")
    frn.add_argument("title")
    frn.add_argument("--private", action="store_true")
    frn.add_argument("--public", action="store_true")

    la = sub.add_parser("later-add", help="加入稍后再看")
    la.add_argument("bvid")

    ld = sub.add_parser("later-del", help="移出稍后再看")
    ld.add_argument("bvid")

    hd = sub.add_parser("history-del", help="删除一条观看历史")
    hd.add_argument("kid")

    sub.add_parser("history-clear", help="清空观看历史")

    sub.add_parser("mcp", help="以 MCP server 方式运行（stdio）")

    ud = sub.add_parser("user-dynamics", help="任意 UP 主的动态")
    ud.add_argument("uid")
    ud.add_argument("--offset", default="")
    ud.add_argument("-n", "--limit", type=int, default=20)

    rpl = sub.add_parser("replies", help="二级回复列表")
    rpl.add_argument("bvid")
    rpl.add_argument("root")
    rpl.add_argument("--page", type=int, default=1)
    rpl.add_argument("-n", "--limit", type=int, default=20)

    cdel = sub.add_parser("comment-delete", help="删除自己的评论")
    cdel.add_argument("bvid")
    cdel.add_argument("rpid")

    ft = sub.add_parser("follow-tags", help="关注分组")
    ft.add_argument("uid")

    tm = sub.add_parser("tag-members", help="分组内的关注")
    tm.add_argument("uid")
    tm.add_argument("tagid", type=int)
    tm.add_argument("--page", type=int, default=1)
    tm.add_argument("-n", "--limit", type=int, default=20)

    bf = sub.add_parser("bangumi-followed", help="我的追番")
    bf.add_argument("uid")
    bf.add_argument("--page", type=int, default=1)
    bf.add_argument("-n", "--limit", type=int, default=20)

    bfl = sub.add_parser("bangumi-follow", help="追番 / 取消追番")
    bfl.add_argument("season_id")
    bfl.add_argument("--undo", action="store_true")

    tl = sub.add_parser("timeline", help="番剧更新表")
    tl.add_argument("--day", type=int, default=1)

    bt = sub.add_parser("batch", help="批量下载（视频/番剧/课程/收藏夹/合集/UP 空间）")
    bt.add_argument("target", help="链接或 ID：BV/ep/ss/md/cheese/favlist/lists")
    bt.add_argument("-o", "--output", type=Path, default=Path("."))
    bt.add_argument("-n", "--limit", type=int, default=0, help="最多下载几个（0 表示全部）")
    bt.add_argument("--quality", type=int, default=80)
    bt.add_argument("--list", action="store_true", help="只解析并列出，不下载")

    sub.add_parser("tui", help="交互式浏览（REPL）")

    ic = sub.add_parser("import-cookies", help="从浏览器导入 cookie")
    ic.add_argument("--browser", choices=["firefox", "chrome"], default="firefox")
    ic.add_argument("--profile", default="", help="直接指定 cookie 数据库路径")

    qual = sub.add_parser("qualities", help="列出视频可用清晰度")
    qual.add_argument("bvid")

    ld.add_argument("room_id")
    ld.add_argument("--seconds", type=int, default=30)
    ld.add_argument("-n", "--limit", type=int, default=100)

    comp = sub.add_parser("completion", help="生成 shell 补全脚本")
    comp.add_argument("shell", choices=["bash", "zsh", "fish"])

    up = sub.add_parser("update", help="检查 / 安装新版本")
    up.add_argument("--check", action="store_true", help="只检查，不安装")

    r = sub.add_parser("api", help="原始 API 调用（调试用）")
    r.add_argument("path")
    r.add_argument("--param", action="append", default=[], metavar="K=V")
    r.add_argument("--wbi", action="store_true")

    return p


def run(args: argparse.Namespace) -> Any:
    cmd = args.command
    if cmd == "doctor":
        from . import doctor

        return doctor.run()
    if cmd == "mcp":
        from .mcp import serve

        raise SystemExit(serve())
    if cmd == "completion":
        return {"script": completion_script(args.shell)}
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
            "profile": auth.PROFILE or "default",
            "credential_file": str(auth.CREDENTIAL_FILE),
            "has_sessdata": bool(cred.get("sessdata")),
            "user": info,
        }
    if cmd == "whoami":
        return api.whoami(auth.client())
    if cmd == "login":
        def state(s: str) -> None:
            print(f"[login] {s}", file=sys.stderr, flush=True)

        cred = auth.qr_login(png=args.png, timeout=args.timeout, on_state=state, profile=args.profile)
        return {"logged_in": True, "profile": args.profile or "default", "uid": cred.get("dedeuserid", "")}
    if cmd == "logout":
        auth.clear_credential()
        return {"logged_out": True}
    if cmd == "search":
        return api.search(
            auth.client(), args.keyword, args.type, args.page, args.limit,
            args.order, args.duration, args.tids,
        )
    if cmd == "video":
        c, bvid = auth.client(), api.bvid_of(args.bvid)
        data = api.video(c, bvid, args.subtitle, args.comments)
        if args.ai:
            data["ai"] = api.ai_summary(c, bvid)
        if args.related:
            data["related"] = api.related(c, bvid)
        if args.parts:
            data["parts"] = api.parts(c, bvid)
        if args.chapters:
            data["chapters"] = api.chapters(c, bvid)
        if args.danmaku:
            data["danmaku"] = api.danmaku(c, bvid)
        return data
    if cmd == "user":
        return api.user(auth.client(), args.uid)
    if cmd == "user-videos":
        return api.user_videos(auth.client(), args.uid, args.page, args.limit, args.order)

    if cmd == "rank":
        return api.rank(auth.client(), args.limit, args.rid)
    if cmd == "history":
        return api.history(auth.client())
    if cmd == "favorites":
        return api.favorites(auth.client())
    if cmd == "watch-later":
        return api.watch_later(auth.client())
    if cmd == "feed":
        return api.dynamic_feed(auth.client(), args.limit, args.page)
    if cmd == "my-dynamics":
        return api.my_dynamics(auth.client(), args.limit, args.offset)
    if cmd == "favorites-items":
        return api.favorites_contents(auth.client(), args.folder_id, args.page, args.limit)
    if cmd == "like":
        return api.like(auth.client(), api.bvid_of(args.bvid), args.undo)
    if cmd == "coin":
        return api.coin(auth.client(), api.bvid_of(args.bvid), args.count, args.also_like)
    if cmd == "triple":
        return api.triple(auth.client(), api.bvid_of(args.bvid))
    if cmd == "follow":
        return api.follow(auth.client(), args.uid, args.undo)
    if cmd == "fav-add":
        return api.favorite_add(auth.client(), api.bvid_of(args.bvid), args.folder_id)
    if cmd == "fav-remove":
        return api.favorite_remove(auth.client(), api.bvid_of(args.bvid), args.folder_id)
    if cmd == "comment":
        return api.comment(auth.client(), api.bvid_of(args.bvid), args.message)
    if cmd == "audio":
        return api.audio(
            auth.client(),
            api.bvid_of(args.bvid),
            args.output,
            segment=args.segment,
            split=not args.no_split,
        )
    if cmd == "daily":
        from . import daily

        return daily.run(
            auth.client(), bvid=args.bvid,
            coins=max(0, min(args.coins, 5)),
            share_video=args.share, watch_video=not args.no_watch,
            jitter=args.jitter,
        )
    if cmd == "frames":
        from . import frames

        out_dir = args.output or Path(tempfile.gettempdir()) / "bcli-frames" / api.bvid_of(args.target)
        return frames.extract(
            auth.client(), api.bvid_of(args.target), out_dir,
            count=args.count, width=args.width, scene=args.scene,
            quality=args.quality, inline=args.inline, keep_video=args.keep_video,
        )
    if cmd == "asr-engines":
        from . import asr

        return asr.list_engines()
    if cmd == "asr":
        from . import asr

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
        result = asr.transcribe(paths, engine=args.engine, model=args.model)
        if args.srt:
            from .media import _srt_time

            cues = []
            for idx, item in enumerate(result.get("items") or [], 1):
                start = (idx - 1) * args.segment
                cues.append(
                    f"{idx}\n{_srt_time(start)} --> {_srt_time(start + args.segment)}\n{item.get('text', '')}\n"
                )
            args.srt.write_text("\n".join(cues), encoding="utf-8")
            result["srt"] = str(args.srt)
        if not args.keep_audio and api.BVID_RE.search(target):
            for p in paths:
                Path(p).unlink(missing_ok=True)
        return {"source": meta, "transcription": result}
    if cmd == "update":
        from . import update

        return update.check() if args.check else update.perform_update()
    if cmd in {"bangumi", "bangumi-rank", "article", "user-articles", "collections"}:
        from . import content

        c = auth.client()
        if cmd == "bangumi":
            return content.bangumi(c, ep_id=args.season_id if args.ep else None,
                                   season_id=None if args.ep else args.season_id)
        if cmd == "bangumi-rank":
            return content.bangumi_rank(c, args.season_type, args.day, args.limit)
        if cmd == "article":
            return content.article(c, args.cvid)
        if cmd == "user-articles":
            return content.user_articles(c, args.mid, args.page, args.limit)
        return content.collections(c, args.mid, args.page, args.limit)

    if cmd == "user-dynamics":
        from . import social2

        return social2.user_dynamics(auth.client(), args.uid, args.offset, args.limit)
    if cmd == "replies":
        from . import social2

        c = auth.client()
        aid = api.video(c, api.bvid_of(args.bvid))["aid"]
        return social2.replies(c, str(aid), args.root, args.page, args.limit)
    if cmd == "comment-delete":
        from . import social2

        c = auth.client()
        aid = api.video(c, api.bvid_of(args.bvid))["aid"]
        return social2.delete_comment(c, str(aid), args.rpid)
    if cmd == "follow-tags":
        from . import social2

        return social2.follow_tags(auth.client(), args.uid)
    if cmd == "tag-members":
        from . import social2

        return social2.tag_members(auth.client(), args.uid, args.tagid, args.page, args.limit)
    if cmd == "bangumi-followed":
        from . import social2

        return social2.bangumi_followed(auth.client(), args.uid, args.page, args.limit)
    if cmd == "bangumi-follow":
        from . import social2

        return social2.bangumi_follow(auth.client(), args.season_id, args.undo)
    if cmd == "timeline":
        from . import content

        return content.timeline(auth.client(), args.day)
    if cmd == "batch":
        from . import batch

        c = auth.client()
        resolved = batch.resolve(c, args.target, args.limit)
        if args.list:
            return resolved
        result = batch.download_all(c, resolved["items"], args.output, args.quality)
        return {"source": resolved["title"], "kind": resolved["kind"], **result}
    if cmd == "tui":
        from .tui import run as tui_run

        raise SystemExit(tui_run())
    if cmd == "import-cookies":
        from . import cookies

        return cookies.import_from(args.browser, args.profile)
    if cmd == "qualities":
        return api.video_qualities(auth.client(), api.bvid_of(args.bvid))
    if cmd == "hot":
        return api.hot(auth.client(), args.limit)
    if cmd == "rcmd":
        return api.recommend(auth.client(), args.limit, args.fresh_type, args.fresh_idx)
    if cmd in {"notifications", "unread", "followings", "fans", "comments", "reply", "like-comment"}:
        from . import social

        c = auth.client()
        if cmd == "notifications":
            return social.messages(c, args.kind, args.page, args.limit)
        if cmd == "unread":
            return social.unread(c)
        if cmd == "followings":
            return social.followings(c, args.uid, args.page, args.limit)
        if cmd == "fans":
            return social.fans(c, args.uid, args.page, args.limit)
        if cmd == "comments":
            return social.comments(c, api.video(c, api.bvid_of(args.bvid))["aid"], args.cursor, args.limit)
        if cmd == "reply":
            return social.reply_comment(c, api.bvid_of(args.bvid), args.message, args.root, args.parent)
        return social.like_comment(c, api.bvid_of(args.bvid), args.rpid, args.undo)

    if cmd in {"download", "subtitle-srt", "danmaku-export"}:
        from . import media

        c = auth.client()
        bvid = api.bvid_of(args.bvid)
        if cmd == "download":
            return media.download_video(c, bvid, args.output, args.quality, args.part, args.audio_only)
        if cmd == "subtitle-srt":
            return media.subtitle_srt(c, bvid, args.output, args.lang)
        if args.format == "ass":
            from .danmaku_ass import export as ass_export

            return ass_export(c, bvid, args.limit)
        return media.danmaku_export(c, bvid, args.format, args.limit)

    if cmd in {"dynamic-post", "dynamic-delete", "fav-create", "fav-delete", "fav-rename",
               "later-add", "later-del", "history-del", "history-clear"}:
        c = auth.client()
        if cmd == "dynamic-post":
            return api.dynamic_post(c, args.text)
        if cmd == "dynamic-delete":
            return api.dynamic_delete(c, args.dynamic_id)
        if cmd == "fav-create":
            return api.favorite_create(c, args.title, args.private)
        if cmd == "fav-delete":
            return api.favorite_delete(c, args.folder_id)
        if cmd == "fav-rename":
            private = True if args.private else (False if args.public else None)
            return api.favorite_rename(c, args.folder_id, args.title, private)
        if cmd == "later-add":
            return api.watch_later_add(c, api.bvid_of(args.bvid))
        if cmd == "later-del":
            return api.watch_later_remove(c, api.bvid_of(args.bvid))
        if cmd == "history-del":
            return api.history_delete(c, args.kid)
        return api.history_clear(c)

    if cmd == "api":
        params = {}
        for item in args.param:
            k, _, val = item.partition("=")
            params[k] = val
        return auth.client().get(args.path, params, wbi=args.wbi)
    raise SystemExit(f"unknown command: {cmd}")


def _ensure_utf8() -> None:
    """Windows consoles default to cp1252 and choke on Chinese help text."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def completion_script(shell: str) -> str:
    parser = build_parser()
    names = " ".join(sorted(next(a for a in parser._actions if a.dest == "command").choices))
    if shell == "bash":
        return f"""_bili_complete() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )
  fi
}}
complete -F _bili_complete bili bcli
"""
    if shell == "zsh":
        return f"""#compdef bili bcli
_bili() {{
  local -a commands
  commands=({names})
  _describe 'command' commands
}}
_bili "$@"
"""
    return f"""complete -c bili -n '__fish_use_subcommand' -a '{names}'
complete -c bcli -n '__fish_use_subcommand' -a '{names}'
"""


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    args = build_parser().parse_args(argv)
    try:
        data = run(args)
        if getattr(args, "fields", ""):
            from .format import pick

            data = pick(data, [f.strip() for f in args.fields.split(",") if f.strip()])
        if getattr(args, "table", False):
            from .format import table

            sys.stdout.write(table(data))
        elif getattr(args, "yaml", False):
            from .format import to_yaml

            sys.stdout.write(to_yaml(data))
        else:
            emit(Envelope.ok(data), pretty=args.pretty)
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
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to users
        emit(Envelope.err("unexpected_error", f"{type(exc).__name__}: {exc}"), pretty=args.pretty)
        return EXIT_API


if __name__ == "__main__":
    sys.exit(main())
