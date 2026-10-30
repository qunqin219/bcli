# Contributing

## 开发环境

```bash
git clone https://github.com/qunqin219/bcli.git
cd bcli
python3 -m venv .venv
.venv/bin/pip install -e ".[qr,dev]"
.venv/bin/python -m unittest discover -s tests -v
```

提交前请确保：

1. `python -m unittest discover -s tests` 全绿（离线，不依赖网络和账号）
2. `bash scripts/smoke.sh` 在已登录环境下全 PASS（可选，需要真实账号）
3. 改了行为就更新 `CHANGELOG.md` 的 `## Unreleased` 段

## 代码约定

- 只用标准库；新增第三方运行时依赖需要先开 issue 讨论
- 所有命令必须返回统一信封 `{ok, schema_version, data, error}`，错误走 `Envelope.err`
- 写操作必须经过 `Client.post`（自动带 `csrf`），不要手拼请求
- 下载媒体一律带 `Range: bytes=0-`，否则 B 站 CDN 返回 567
- 注释只写“为什么”，不写“是什么”

## 提交信息

`type: subject`，type 取 `feat` / `fix` / `docs` / `test` / `ci` / `chore` / `refactor`。
正文用中文或英文都可，说明动机和影响面。

## 发布流程（维护者）

1. 更新 `CHANGELOG.md`：把 `## Unreleased` 改成目标版本号
2. 同步版本号：`pyproject.toml`
3. 提交 `release: vX.Y.Z`，打 tag `vX.Y.Z` 并推送
4. CI 自动完成：构建三平台二进制 + wheel/sdist → 建 Release（正文取自 CHANGELOG）→ 更新 Homebrew tap

发版前自查：

- [ ] 离线单测 + CI 全绿
- [ ] `CHANGELOG.md` 有对应版本段落（否则 Release 正文会降级成链接）
- [ ] 写操作/登录等敏感改动在真号上验证过
- [ ] 没有把 `build/`、`dist/`、凭证、`.venv` 提交进来
