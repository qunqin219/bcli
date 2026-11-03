"""每日经验任务：登录、观看、分享、投币。

B 站每日经验上限 65：登录 5 + 观看 5 + 分享 5 + 投币 10×5（封顶 50）。
每个动作做完立刻回读 /x/member/web/exp/reward，报告哪个状态位真的变了，
不靠"接口返回 0 就算成功"。
"""

from __future__ import annotations

import random
import time
from typing import Any

from . import api
from .http import Client

REWARD = "/x/member/web/exp/reward"


def status(c: Client) -> dict[str, Any]:
    return c.get(REWARD) or {}


def exp(c: Client) -> int:
    nav = c.get("/x/web-interface/nav", auth_required=False) or {}
    return int((nav.get("level_info") or {}).get("current_exp") or 0)


def watch(c: Client, bvid: str, seconds: int = 300) -> dict[str, Any]:
    info = c.get("/x/web-interface/view", {"bvid": bvid}) or {}
    cid = info.get("cid")
    if not cid:
        raise ValueError(f"拿不到 cid: {bvid}")
    now = int(time.time())
    c.post(
        "/x/click-interface/web/heartbeat",
        {
            "aid": info.get("aid"),
            "bvid": bvid,
            "cid": cid,
            "played_time": seconds,
            "realtime": seconds,
            "start_ts": now - seconds,
            "type": 3,
            "sub_type": 0,
            "dt": 2,
            "play_type": 0,
            "last_play_progress": seconds,
            "outer": 0,
        },
    )
    return {"bvid": bvid, "seconds": seconds}


def share(c: Client, bvid: str) -> dict[str, Any]:
    c.post("/x/web-interface/share/add", {"bvid": bvid})
    return {"bvid": bvid, "shared": True}


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def run(
    c: Client,
    bvid: str | None = None,
    coins: int = 0,
    share_video: bool = False,
    watch_video: bool = True,
    jitter: int = 0,
) -> dict[str, Any]:
    """跑一轮每日任务，返回动作结果与经验增量。

    jitter: 开始前随机等待 0..jitter 秒；动作之间再随机停 8-30 秒，
    避免每天都在同一秒、同一节奏打卡。
    """
    _sleep(random.uniform(0, jitter) if jitter > 0 else 0)
    before_status = status(c)
    before_exp = exp(c)
    actions: list[dict[str, Any]] = []

    pool_rows = api.recommend(c, random.randint(8, 18))
    pool = [r["bvid"] for r in pool_rows if r.get("bvid")]
    if not pool:
        raise RuntimeError("拿不到可用的视频，无法完成观看/分享")

    if bvid:
        watch_target = share_target = bvid
    else:
        watch_target = random.choice(pool)
        share_target = random.choice([b for b in pool if b != watch_target] or pool)

    ops: list[str] = []
    if watch_video and not before_status.get("watch"):
        ops.append("watch")
    if share_video and not before_status.get("share"):
        ops.append("share")
    if coins and len([bv for bv in pool]) > 0:
        ops.append("coins")
    # 顺序也随机：有时先看后分享，有时反过来
    random.shuffle(ops)

    coins_targets = random.sample(pool, min(coins, len(pool))) if "coins" in ops else []

    for op in ops:
        _sleep(random.uniform(30, 150))
        if op == "watch":
            actions.append({"action": "watch", **watch(c, watch_target, seconds=random.randint(180, 600))})
        elif op == "share":
            actions.append({"action": "share", **share(c, share_target)})
        else:
            for bv in coins_targets:
                _sleep(random.uniform(20, 90))
                try:
                    actions.append({"action": "coin", **api.coin(c, bv, 1)})
                except Exception as exc:  # noqa: BLE001
                    actions.append({"action": "coin", "bvid": bv, "error": str(exc)})

    target = watch_target
    # B 站的状态位有写入延迟：分享成功后立刻读，可能还是 false。
    # 动作做完就多读几次，直到 share/watch 变成 true 或经验值稳定下来。
    after_status = status(c)
    after_exp = exp(c)
    if actions:
        for _ in range(10):
            if after_exp > before_exp and after_status.get("watch") and after_status.get("share"):
                break
            _sleep(2)
            after_status = status(c)
            after_exp = exp(c)
    return {
        "target": target,
        "before": before_status,
        "after": after_status,
        "exp_before": before_exp,
        "exp_after": after_exp,
        "exp_gained": after_exp - before_exp,
        "actions": actions,
        "remaining": {
            "login": not after_status.get("login"),
            "watch": not after_status.get("watch"),
            "share": not after_status.get("share"),
            "coins_left_for_exp": max(0, 5 - int(after_status.get("coins") or 0)),
        },
    }
