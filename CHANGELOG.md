# Changelog

## 0.4.1

- 移除直播支持：删除 `live`、`live-danmaku`、直播搜索与对应 MCP 工具

## 0.4.0

- 直播弹幕：`live-danmaku`（纯标准库 WebSocket，匿名连接，实验性）
- 二级回复 `replies`、删评论 `comment-delete`
- 任意 UP 主动态 `user-dynamics`、关注分组 `follow-tags` / `tag-members`
- 追番列表/追番开关 `bangumi-followed` / `bangumi-follow`、番剧更新表 `timeline`
- 视频清晰度列表 `qualities`；下载支持 `--part` 与 `--audio-only`
- 搜索新增 article / live / bangumi；直播搜索走独立接口
- `--table` 人类可读表格；客户端限流（`BILI_RATE`）与磁盘缓存（`BILI_CACHE_TTL`）
- MCP 写入工具（`BILI_MCP_WRITE=1` 开启）：点赞、关注
- Windows arm64 预编译二进制
- 异常兜底：任何未预期异常都返回 `unexpected_error` 信封而不是 traceback

## 0.3.0

- 新增内容类型：番剧（`bangumi` / `bangumi-rank`）、直播（`live`）、专栏（`article` /
  `user-articles`）、合集与系列（`collections`）
- 新增社交能力：消息中心（`notifications` / `unread`）、关注与粉丝列表、评论翻页、
  回复评论、评论点赞
- 新增媒体能力：`download`（DASH 音视频合并为 mp4，可选清晰度）、`subtitle-srt`、
  `danmaku-export`
- 新增账号管理：收藏夹增删改、稍后再看加入/移除、历史删除/清空、发/删动态
- 搜索支持排序、时长、分区过滤；`rank --rid` 按分区；`user-videos --order`
- ASR 支持批量转写与 `--srt` 导出
- 新增 `bili mcp`：16 个只读工具，stdio JSON-RPC，可直接挂到 Claude Code / Codex
- 新增 `bili doctor` 环境自检、`bili completion` shell 补全
- 全局 `--yaml` / `--fields` 输出控制；多账号 `BCLI_PROFILE` 与 `login --profile`

## 0.2.3

- 发布产物新增 `checksums.txt`，用户可自行校验下载的二进制
- 新增 Linux arm64 预编译二进制，Homebrew formula 同步支持
- HTTP 层加入有界重试与退避：412/429/5xx 与网络错误会重试，尊重 `Retry-After`，`BILI_RETRIES` 可调
- 新增联网集成测试（`BILI_INTEGRATION=1`）与每周 CI 任务
- 新增英文 README
- 版本号改为单一来源（`importlib.metadata`，避免 `__init__` 与 `pyproject` 漂移）
- 补齐项目治理文件：CONTRIBUTING / SECURITY / issue 模板 / PR 模板 / dependabot
- `.gitignore` 覆盖 build、dist、spec 等构建产物

## 0.2.2

- 发布流程自动化：打 tag 后自动更新 Homebrew tap 的 formula（版本、URL、sha256）

## 0.2.1

- 新增 `bili update` / `bili update --check`：二进制安装可原地自更新，Homebrew 用户提示走 `brew upgrade`
- 版本比较、平台资产映射有离线单测

## 0.2.0

- 新增写操作：`like` / `coin` / `triple` / `follow` / `fav-add` / `fav-remove` / `comment`
- 新增 `favorites-items`，可翻页查看收藏夹内容
- `feed` / `my-dynamics` 支持翻页
- `video` 支持 `--ai` / `--related` / `--parts` / `--chapters` / `--danmaku`
- HTTP 层支持 POST + CSRF；自动解压 gzip/deflate 响应（弹幕 XML 是 deflate）
- 匿名用户也能取 WBI 密钥（`nav` 返回 -101 时仍取 `wbi_img`）
- 取消点赞参数修正为 `like=2`（`0` 会被 B 站拒绝）
- 包名改为 `bilicli`，命令 `bili`，保留 `bcli` 别名
- 增加离线单元测试、CI、LICENSE

## 0.1.0

- 首个版本：登录、搜索、视频详情/字幕/评论、UP 主、热门、排行、历史、收藏夹、稍后再看、动态、音频下载、SenseVoice 转写
