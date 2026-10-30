# Changelog

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
