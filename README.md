# bcli

一个自己维护的 B 站命令行工具。零第三方运行时依赖（`qrcode` 仅用于把登录二维码存成 PNG，可选）。

```bash
bcli status                 # 登录状态 + 账号
bcli whoami
bcli login --png /tmp/qr.png
bcli search "影视飓风" -n 10  # --type user 搜 UP 主
bcli video BV1xxxxxxxxx -s -c  # -s 字幕，-c 评论
bcli user 946974
bcli user-videos 946974 -n 10
bcli hot / rank
bcli history / favorites / watch-later / feed / my-dynamics
bcli audio BV1xxxxxxxxx -o /tmp/a --segment 300   # 切 16k 单声道 WAV
bcli asr BV1xxxxxxxxx --keep-audio                # 下载 + 切分 + SenseVoice 转写
```

## 输出契约

所有命令输出同一个信封，成功和失败都是合法 JSON：

```json
{"ok": true, "schema_version": "1", "data": ...}
{"ok": false, "schema_version": "1", "error": {"code": "not_authenticated", "message": "..."}}
```

退出码：`0` 成功，`1` 接口/参数错误，`2` 未登录，`3` 网络错误。

## 凭证

`~/.config/bcli/credential.json`（0600），字段为 `sessdata` / `bili_jct` / `dedeuserid` / `ac_time_value`。
可用环境变量覆盖：`BCLI_SESSDATA`、`BCLI_JCT`、`BCLI_UID`；配置目录可用 `BCLI_CONFIG_DIR` 改。

`bcli login` 生成扫码二维码并轮询，cookie 用 `http.cookiejar` 抓 Set-Cookie——只解析回调 URL 会拿到空 SESSDATA。

## 为什么不用现成的库

`bilibili-api-python` 这类中间层一改接口就整条命令失效，而且 WBI 签名、Cookie、错误码都不可控。
这里只有 stdlib：`urllib` + `json` + `http.cookiejar`，WBI 签名自己实现（置换表 + MD5），下载强制带
`Range: bytes=0-`（B 站 CDN 对无 Range 的整文件 GET 返回 HTTP 567）。

## ASR

`bcli asr` 默认调用 `/root/venvs/sensevoice/bin/python` 里的 worker，模型目录 `/root/models/SenseVoiceSmall`。
可用 `BCLI_ASR_PYTHON`、`BCLI_ASR_MODEL`、`BCLI_ASR_WORKER` 覆盖。

## 开发

```bash
python3 -m venv /root/venvs/bcli
/root/venvs/bcli/bin/pip install -e ".[qr]"
bash scripts/smoke.sh        # 只读命令冒烟测试
```
