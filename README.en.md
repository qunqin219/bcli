# bili

[![ci](https://github.com/qunqin219/bcli/actions/workflows/ci.yml/badge.svg)](https://github.com/qunqin219/bcli/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/qunqin219/bcli)](https://github.com/qunqin219/bcli/releases/latest)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[中文](README.md) · **English**

A zero-dependency Bilibili CLI for terminals and agents. Every command prints
the same JSON envelope, so scripts and LLM agents can parse it without guessing.

```bash
bili status                     # auth state + account
bili search "keyword" -n 10     # --type user to search creators
bili video BV1xxxxxxxxx -s -c   # -s subtitles, -c comments
bili video BV1xxxxxxxxx --ai --danmaku --chapters --parts --related
bili user 946974
bili user-videos 946974 -n 10
bili hot / rank
bili history / favorites / favorites-items / watch-later / feed / my-dynamics
bili audio BV1xxxxxxxxx -o ./a --segment 300
bili asr BV1xxxxxxxxx --keep-audio
bili update --check / bili update

# more content types / social / media
bili bangumi 33378 / bili live 6 / bili article 45123193 / bili collections 946974
bili notifications --kind reply / bili unread / bili followings 946974
bili comments BV1xxxxxxxxx --cursor 3
bili download BV1xxxxxxxxx --quality 80 / bili subtitle-srt BV1xxxxxxxxx -o a.srt
bili danmaku-export BV1xxxxxxxxx

# tooling
bili doctor            # self-diagnosis
bili mcp               # run as an MCP server over stdio
bili completion bash
```

Global output flags: `--yaml`, `--fields name,uid`, `--pretty`.
Multiple accounts: `BCLI_PROFILE=work` or `bili login --profile work`.

## Install

```bash
# macOS (Apple Silicon) and Linux x86_64 / arm64
brew tap qunqin219/tap && brew install bili

# or grab a binary
# https://github.com/qunqin219/bcli/releases/latest

# from source
python3 -m venv .venv
.venv/bin/pip install -e ".[qr]"
```

Requires Python 3.11+ for source installs. `audio` splitting needs `ffmpeg`.

## Output contract

```json
{"ok": true,  "schema_version": "1", "data": ...}
{"ok": false, "schema_version": "1", "error": {"code": "not_authenticated", "message": "..."}}
```

Exit codes: `0` ok, `1` API/argument error, `2` not authenticated, `3` network error.
Error codes: `not_authenticated`, `not_found`, `api_error`, `network_error`,
`invalid_argument`, `missing_dependency`, `runtime_error`.

## Auth

Credentials live in `~/.config/bcli/credential.json` (mode 600). Override with
`BCLI_SESSDATA`, `BCLI_JCT`, `BCLI_UID`, or move the directory with `BCLI_CONFIG_DIR`.

`bili login` renders a QR (save it with `--png qr.png`) and captures the session
cookies through `http.cookiejar` — parsing the callback URL alone yields an empty
SESSDATA, which is a bug in several existing wrappers.

## Updating

- Homebrew: `brew upgrade bili`
- Binary: `bili update` (in-place, atomic replace; refuses to touch a Cellar install)
- Source: `git pull && pip install -e .`

## ASR

`bili asr` downloads the audio, splits it into 16 kHz mono WAV segments and runs
[SenseVoice-Small](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) in a
separate interpreter (torch/funasr are not dependencies of this CLI):

```bash
python3 -m venv .venv-asr
.venv-asr/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv-asr/bin/pip install funasr
hf download FunAudioLLM/SenseVoiceSmall --local-dir ~/models/SenseVoiceSmall
```

Point `~/.config/bcli/config.json` at it:

```json
{"asr_python": "/path/.venv-asr/bin/python", "asr_model": "/path/models/SenseVoiceSmall"}
```

## Why not use an existing wrapper

Existing wrappers break whenever the upstream API changes; signing, cookies and
error codes are out of reach. This CLI keeps the HTTP layer in `urllib`, signs
WBI itself, always sends `Range: bytes=0-` for media (the CDN answers plain GETs
with HTTP 567) and keeps the output schema stable.

## Privacy

No telemetry. Requests only go to `api.bilibili.com`, `passport.bilibili.com`,
Bilibili CDNs and the GitHub Releases API for `bili update`.

Unofficial project, not affiliated with Bilibili. Write commands act on your real
account — use them at your own discretion.

## Development

```bash
python -m unittest discover -s tests          # offline, no credentials
BILI_INTEGRATION=1 python -m unittest tests.test_integration -v   # live, read-only
bash scripts/smoke.sh                          # CLI smoke test (needs login)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT
