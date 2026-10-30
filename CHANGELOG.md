# Changelog

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
