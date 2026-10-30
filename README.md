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
bili asr BV1xxxxxxxxx --keep-audio             # 下载 + 切分 + SenseVoice 转写
```

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[qr]"        # 不需要 PNG 二维码可去掉 [qr]
.venv/bin/bili --version
```

要求 Python 3.11+。`audio` 切分需要系统有 `ffmpeg`；`--no-split` 则不需要。

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
  "asr_python": "/path/to/env/bin/python",
  "asr_model": "/path/to/SenseVoiceSmall",
  "asr_worker": "/path/to/scripts/asr_worker.py"
}
```

对应环境变量：`BCLI_ASR_PYTHON`、`BCLI_ASR_MODEL`、`BCLI_ASR_WORKER`。

## ASR

`bili asr` 把视频下载成 16k 单声道 WAV 分段，再调用 `scripts/asr_worker.py`，用 [SenseVoice-Small](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) 转写。模型和 torch 不在本 CLI 的依赖里，worker 在独立解释器中运行：

```bash
python3 -m venv .venv-asr
.venv-asr/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv-asr/bin/pip install funasr

# 下载模型（Hugging Face）
hf download FunAudioLLM/SenseVoiceSmall --local-dir ~/models/SenseVoiceSmall
```

然后在 `~/.config/bcli/config.json` 里把 `asr_python` 指向 `.venv-asr/bin/python`。默认模型目录是 `~/models/SenseVoiceSmall`。

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
尚未实现：发动态、番剧/直播、视频流下载。包名 `bilicli`，尚未发布到 PyPI。

## License

MIT
