# bcli

一个自己维护的 B 站命令行工具。**零第三方运行时依赖**：只用 Python 标准库（`urllib`、`json`、`http.cookiejar`、`argparse`），WBI 签名自己实现。`qrcode` + `pillow` 只是可选，用来把登录二维码存成 PNG。

```bash
bili status                    # 登录状态 + 账号
bili whoami
bili login --png qr.png        # 扫码登录，二维码另存为 PNG
bili search "影视飓风" -n 10    # --type user 搜 UP 主
bili video BV1xxxxxxxxx -s -c  # -s 字幕全文，-c 评论
bili user 946974
bili user-videos 946974 -n 10
bili hot / rank
bili history / favorites / watch-later / feed / my-dynamics
bili favorites-items 4425429009 --page 1 # 收藏夹里的视频
bili video BV1xxxxxxxxx --ai --danmaku --chapters --parts --related

# 写操作（会真的改动账号）
bili like BV1xxxxxxxxx / bili like BV1xxxxxxxxx --undo
bili coin BV1xxxxxxxxx -n 2 --also-like
bili triple BV1xxxxxxxxx
bili follow 946974 / bili follow 946974 --undo
bili fav-add BV1xxxxxxxxx 4425429009 / bili fav-remove BV1xxxxxxxxx 4425429009
bili comment BV1xxxxxxxxx "说点什么"
bili audio BV1xxxxxxxxx -o ./a --segment 300   # 切 16k 单声道 WAV
bili asr BV1xxxxxxxxx --keep-audio --srt a.srt # 转写并可导出 SRT

# 更多内容类型
bili bangumi 33378 / bili bangumi-rank
bili article 45123193 / bili user-articles 946974 / bili collections 946974

# 社交
bili notifications --kind reply / bili unread
bili followings 946974 / bili fans 946974
bili comments BV1xxxxxxxxx --cursor 3 / bili reply BV1xxxxxxxxx "说点什么" / bili like-comment BV1xxxxxxxxx 12345

# 媒体
bili download BV1xxxxxxxxx -o ./v --quality 80   # 合并为 mp4
bili batch "https://space.bilibili.com/946974/lists?sid=2046621&type=season" -o ./v -n 5
bili batch ep395211 --list          # 番剧剧集解析
bili danmaku-export BV1xxxxxxxxx --format ass -o danmaku.ass
bili tui                            # 交互式浏览
bili import-cookies --browser firefox
bili subtitle-srt BV1xxxxxxxxx -o a.srt
bili danmaku-export BV1xxxxxxxxx --format txt

# 账号管理
bili fav-create "新收藏夹" / bili fav-rename 123 "改名" / bili fav-delete 123
bili later-add BV1xxxxxxxxx / bili later-del BV1xxxxxxxxx
bili history-del <kid> / bili history-clear
bili dynamic-post "纯文本动态" / bili dynamic-delete <id>

# 番剧 / 空间
bili timeline / bili bangumi-followed 946974 / bili bangumi-follow 33378
bili user-dynamics 946974 / bili follow-tags 946974
bili qualities BV1xxxxxxxxx / bili download BV1xxxxxxxxx --part 2 --audio-only

# 工具
bili doctor            # 环境自检
bili mcp               # 以 MCP server 方式运行（stdio）
bili completion bash > /etc/bash_completion.d/bili
```

全局输出控制：`--json`（默认）、`--yaml`、`--table`、`--fields name,uid`、`--pretty`。
限流与缓存：`BILI_RATE`（每秒请求数，默认 5）、`BILI_CACHE_TTL`（秒，默认关闭）。
多账号：环境变量 `BCLI_PROFILE=work`，或 `bili login --profile work`。

## 安装

```bash
# macOS (Apple Silicon) / Linux x86_64
brew tap qunqin219/tap && brew install bili

# 或者直接下二进制
# https://github.com/qunqin219/bcli/releases/latest

# 源码安装
python3 -m venv .venv
.venv/bin/pip install -e ".[qr]"        # 不需要 PNG 二维码可去掉 [qr]
.venv/bin/bili --version
```

要求 Python 3.11+。`audio` 切分需要系统有 `ffmpeg`；`--no-split` 则不需要。

## 更新

```bash
bili update --check   # 看有没有新版本
bili update           # 二进制安装：自动下载并原地替换
```

- Homebrew 装的：提示用 `brew upgrade bili`（不要自替换，会破坏 Cellar 记录）
- 源码装的：提示 `git pull && pip install -e .`
- 下载二进制的：自动替换当前可执行文件，失败会回滚（先写临时文件再原子 rename）

## 输出契约

所有命令输出同一个信封，成功和失败都是合法 JSON，便于脚本和 agent 消费：

```json
{"ok": true,  "schema_version": "1", "data": ...}
{"ok": false, "schema_version": "1", "error": {"code": "not_authenticated", "message": "..."}}
```

退出码：`0` 成功，`1` 接口/参数错误，`2` 未登录，`3` 网络错误。

错误码：`not_authenticated`、`not_found`、`api_error`、`network_error`、`invalid_argument`、`missing_dependency`、`runtime_error`。

## 凭证

默认存在 `~/.config/bcli/credential.json`（权限 600），字段 `sessdata` / `bili_jct` / `dedeuserid` / `ac_time_value`。

- 目录可用 `BCLI_CONFIG_DIR` 改
- 凭据可用 `BCLI_SESSDATA`、`BCLI_JCT`、`BCLI_UID` 覆盖（适合 CI，不落盘）

`bili login` 会生成二维码、轮询扫码状态，并用 `http.cookiejar` 从 `Set-Cookie` 里取凭证——只解析回调 URL 的话 SESSDATA 会是空的。

## 配置文件（可选）

`~/.config/bcli/config.json`，环境变量优先级更高：

```json
{
  "asr_engine": "sensevoice",
  "asr_python": "/path/to/env/bin/python",
  "asr_model": "/path/to/SenseVoiceSmall",
  "asr_qwen_python": "/path/to/qwen-env/bin/python",
  "asr_qwen_model": "/path/to/Qwen3-ASR-0.6B",
  "asr_worker": "/path/to/scripts/asr_worker.py"
}
```

对应环境变量：`BCLI_ASR_ENGINE`、`BCLI_ASR_PYTHON`、`BCLI_ASR_MODEL`、`BCLI_ASR_QWEN_PYTHON`、`BCLI_ASR_QWEN_MODEL`、`BCLI_ASR_WORKER`。

## ASR

`bili asr` 把视频下载成 16k 单声道 WAV 分段，再交给外部 worker 转写。torch 不在本 CLI 的依赖里，每个引擎跑在自己的解释器中。支持两个引擎，可同时安装：

| 引擎 | 模型 | 特点 |
|---|---|---|
| `sensevoice`（默认） | SenseVoice-Small（900 MB） | 非自回归，CPU 上 RTF≈0.1，中文强、带标点；英文术语弱 |
| `qwen3-asr` | Qwen3-ASR-0.6B（1.8 GB） | 自回归，CPU 上慢约 8 倍；中英混说、术语明显更准，支持 52 种语言 |

```bash
# SenseVoice
python3 -m venv .venv-asr && .venv-asr/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv-asr/bin/pip install funasr
hf download FunAudioLLM/SenseVoiceSmall --local-dir ~/models/SenseVoiceSmall

# Qwen3-ASR
python3 -m venv .venv-qwen && .venv-qwen/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-qwen/bin/pip install qwen-asr
hf download Qwen/Qwen3-ASR-0.6B --local-dir ~/models/Qwen3-ASR-0.6B
```

把 `asr_python` / `asr_qwen_python` 指向各自解释器，`asr_model` / `asr_qwen_model` 指向模型目录。然后：

```bash
bili asr-engines                              # 看检测到了哪些引擎、路径对不对
bili asr BV1xxxxxxxxx                         # 用配置里的默认引擎
bili asr BV1xxxxxxxxx --engine qwen3-asr      # 这一条换引擎
bili asr BV1xxxxxxxxx --engine auto           # 自动选第一个可用引擎
```

Qwen3-ASR 的 dtype 可用 `BCLI_QWEN_ASR_DTYPE` 控制（`float32` 默认，`bfloat16` 省内存但 CPU 上更慢）。

## 为什么不用现成的库

`bilibili-api-python` 这类中间层一改接口就整条命令失效，WBI 签名、Cookie、错误码都不可控。这里的取舍是：

- HTTP 用 `urllib`，签名自己做（置换表 + MD5），失效了能立刻修
- 下载强制带 `Range: bytes=0-`——B 站 CDN 对无 Range 的整文件 GET 返回 HTTP 567
- 输出结构固定，不随上游 SDK 的对象结构变化

## 开发

```bash
bash scripts/smoke.sh     # 15 项只读命令冒烟测试（需要已登录）
```

## 状态

v0.2.0：只读命令、写操作（点赞/投币/三连/关注/收藏/评论）、音频下载、ASR。
尚未实现：发动态、番剧/直播、视频流下载。
分发渠道：GitHub Releases（三平台二进制 + wheel/sdist）与 Homebrew tap；暂不发布 PyPI。

## 维护与版本策略

- 语义化版本：破坏输出结构的改动进大版本，新命令进次版本，修 bug 进补丁版本
- 每个 release 的正文直接取自 `CHANGELOG.md` 对应段落，不靠自动生成的 commit 列表
- 只维护最新 release；旧版本不保证修 bug
- 变更流程、发版清单见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 隐私与数据

- 不做任何遥测或统计上报
- 凭证只存在本机 `~/.config/bcli/credential.json`（0600）
- 请求只发往 `api.bilibili.com` / `passport.bilibili.com` / B 站 CDN
- `bili update` 只访问 GitHub Releases API，用于检查新版本

## 免责声明

本项目是非官方工具，与哔哩哔哩无关联。使用者需自行遵守 B 站用户协议；
写操作（点赞、投币、评论、关注）会产生真实的账号行为，请自行判断。

## License

MIT
