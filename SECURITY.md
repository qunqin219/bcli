# Security Policy

## 支持的版本

只对最新 release 提供安全修复。

## 报告问题

请**不要**开 public issue。用 GitHub 的私密漏洞报告：
https://github.com/qunqin219/bcli/security/advisories/new

或者发邮件到项目主页上的联系方式，标题带 `[bcli security]`。

## 范围

- 凭证处理：`~/.config/bcli/credential.json` 落盘权限、日志里是否泄露 SESSDATA/bili_jct
- 网络请求：是否存在把凭证发往非 B 站域名的路径
- 下载与自更新：`bili update` 的替换逻辑是否可被中间人或恶意资产利用
- 依赖：本项目运行时零第三方依赖，`qrcode`/`pillow` 仅用于生成二维码图片

## 不在范围

- B 站服务端自身的问题
- 因违反 B 站用户协议导致的账号处罚
- 用户自己把凭证贴到公开地方
