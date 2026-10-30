# Third-party notices

运行时零依赖。以下组件只出现在特定安装方式中：

| 组件 | 用途 | 许可 | 出现位置 |
| --- | --- | --- | --- |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | 把登录二维码渲染成 PNG | BSD-3-Clause | `pip install -e ".[qr]"`、预编译二进制 |
| [Pillow](https://python-pillow.org/) | qrcode 的 PNG 后端 | HPND | 同上 |
| PyInstaller | 打包预编译二进制 | GPL-2.0-with-exception | 仅构建期，不随源码分发 |

未安装 `[qr]` 时，`bili login` 只打印二维码链接，其余功能不受影响。
