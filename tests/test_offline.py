"""Offline unit tests — no network, no credentials."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from bilicli import SCHEMA_VERSION
from bilicli.api import _safe_name, bvid_of
from bilicli.cli import Envelope
from bilicli.http import MIXIN_KEY_ENC_TAB, Client


class TestHelpers(unittest.TestCase):
    def test_bvid_from_url(self):
        self.assertEqual(bvid_of("https://www.bilibili.com/video/BV1xrnz6gEVD/?p=2"), "BV1xrnz6gEVD")

    def test_bvid_invalid(self):
        with self.assertRaises(ValueError):
            bvid_of("BV123")

    def test_safe_name_strips_separators(self):
        self.assertEqual(_safe_name('a/b:c*?"<>|'), "a_b_c______")
        self.assertEqual(_safe_name("   "), "audio")


class TestEnvelope(unittest.TestCase):
    def test_ok(self):
        payload = Envelope.ok({"x": 1})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)

    def test_error(self):
        payload = Envelope.err("not_found", "gone", {"code": -404})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "not_found")
        json.dumps(payload)  # must stay serialisable


class TestWBI(unittest.TestCase):
    def test_mixin_table_is_a_permutation(self):
        self.assertEqual(sorted(MIXIN_KEY_ENC_TAB), list(range(64)))

    def test_sign_adds_rid_and_sorts(self):
        c = Client({"sessdata": "x"})
        with mock.patch.object(Client, "wbi_keys", return_value=("a" * 32, "b" * 32)):
            signed = c.sign_wbi({"foo": "bar", "baz": "q u o"})
            stripped = c.sign_wbi({"x": "!a'(b)*"})
        self.assertIn("w_rid", signed)
        self.assertEqual(len(signed["w_rid"]), 32)
        self.assertEqual(signed["foo"], "bar")
        # only the four banned characters are stripped; spaces are urlencoded later
        self.assertEqual(signed["baz"], "q u o")
        self.assertEqual(stripped["x"], "ab")


class TestConfig(unittest.TestCase):
    def test_env_overrides_file(self):
        from bilicli import config

        with mock.patch.dict(os.environ, {"BCLI_ASR_MODEL": "/env/model"}):
            self.assertEqual(config.get("asr_model"), "/env/model")

    def test_missing_returns_default(self):
        from bilicli import config

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(config, "_file", return_value={}):
                self.assertEqual(config.get("nope", "fallback"), "fallback")


class TestRetry(unittest.TestCase):
    def _http_error(self, code):
        import io
        import urllib.error

        return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(b""))

    def test_retries_then_succeeds(self):
        from bilicli.http import Client

        c = Client(retries=2)
        calls = {"n": 0}

        class Resp:
            headers = {"Content-Type": "application/json"}

            def read(self):
                return b'{"code":0,"data":{"ok":1}}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise self._http_error(503)
            return Resp()

        with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch.object(Client, "_sleep_backoff", lambda *a, **k: None):
            self.assertEqual(c.get("/x"), {"ok": 1})
        self.assertEqual(calls["n"], 3)

    def test_gives_up_after_retries(self):
        from bilicli.http import Client, NetworkError

        c = Client(retries=1)
        with mock.patch("urllib.request.urlopen", side_effect=self._http_error(502)), mock.patch.object(Client, "_sleep_backoff", lambda *a, **k: None):
            with self.assertRaises(NetworkError):
                c.get("/x")

    def test_does_not_retry_404(self):
        from bilicli.http import Client, NetworkError

        c = Client(retries=3)
        with mock.patch("urllib.request.urlopen", side_effect=self._http_error(404)):
            with self.assertRaises(NetworkError):
                c.get("/x")


class TestParsing(unittest.TestCase):
    def test_parse_keeps_lists_and_ints(self):
        c = Client()
        self.assertEqual(c._parse(b'{"code":0,"data":[1,2]}', "/x"), [1, 2])
        self.assertEqual(c._parse(b'{"code":0,"data":1}', "/x"), 1)
        self.assertEqual(c._parse(b'{"code":0,"data":null}', "/x"), {})

    def test_parse_maps_codes(self):
        from bilicli.http import ApiError, AuthError

        c = Client()
        with self.assertRaises(AuthError):
            c._parse(b'{"code":-101,"message":"no"}', "/x")
        with self.assertRaises(ApiError):
            c._parse(b'{"code":-400,"message":"bad"}', "/x")


class TestWrites(unittest.TestCase):
    def test_post_requires_csrf(self):
        from bilicli.http import AuthError

        c = Client({"sessdata": "s"})
        with self.assertRaises(AuthError):
            c.post("/x/test", {"a": 1})


class TestFormat(unittest.TestCase):
    def test_yaml_roundtrip_shape(self):
        from bilicli.format import to_yaml

        text = to_yaml({"a": 1, "b": ["x", "y"], "c": {"d": True}})
        self.assertIn("a: 1", text)
        self.assertIn("- x", text)
        self.assertIn("d: true", text)

    def test_yaml_quotes_unsafe_strings(self):
        from bilicli.format import to_yaml

        self.assertIn('"a: b"', to_yaml({"k": "a: b"}))

    def test_pick_fields(self):
        from bilicli.format import pick

        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        self.assertEqual(pick(data, ["a"]), [{"a": 1}, {"a": 3}])
        self.assertEqual(pick({"a": 1, "b": 2}, []), {"a": 1, "b": 2})


class TestTable(unittest.TestCase):
    def test_table_aligns(self):
        from bilicli.format import table

        text = table([{"a": 1, "bb": "x"}, {"a": 22, "bb": "yy"}])
        self.assertIn("bb", text)
        self.assertIn("--", text)
        self.assertEqual(len(text.strip().splitlines()), 4)


class TestBatchResolve(unittest.TestCase):
    def test_kind_detection(self):
        from bilicli.batch import _kind_of

        self.assertEqual(_kind_of("BV1xrnz6gEVD")[0], "video")
        self.assertEqual(_kind_of("https://www.bilibili.com/video/BV1xrnz6gEVD")[0], "video")
        self.assertEqual(_kind_of("ep395211")[0], "bangumi")
        self.assertEqual(_kind_of("https://www.bilibili.com/bangumi/play/ss38221")[0], "bangumi")
        self.assertEqual(_kind_of("https://www.bilibili.com/cheese/play/ep6902")[0], "course")
        self.assertEqual(_kind_of("https://space.bilibili.com/1/favlist?fid=2&ftype=create")[0], "fav")
        self.assertEqual(_kind_of("https://space.bilibili.com/1/lists?sid=2&type=season")[0], "list")


class TestAss(unittest.TestCase):
    def test_convert_basic(self):
        from bilicli.danmaku_ass import convert

        xml = (
            "<i><d p=\"1.5,1,25,16777215,0,0,0,0\">hello</d>"
            "<d p=\"2.0,5,25,255,0,0,0,0\">top</d></i>"
        )
        ass = convert(xml)
        self.assertIn("[Script Info]", ass)
        self.assertEqual(ass.count("Dialogue:"), 2)
        self.assertIn("hello", ass)
        self.assertIn("\\an8", ass)


class TestAsrEngines(unittest.TestCase):
    def test_both_engines_registered(self):
        from bilicli import asr

        names = {e["engine"] for e in asr.list_engines()["engines"]}
        self.assertEqual(names, {"sensevoice", "qwen3-asr", "groq"})

    def test_aliases(self):
        from bilicli import asr

        self.assertEqual(asr.ALIASES["qwen"], "qwen3-asr")
        self.assertEqual(asr.ALIASES["sv"], "sensevoice")

    def test_unavailable_engine_raises(self):
        import os
        from unittest import mock

        from bilicli import asr

        env = {
            "BCLI_ASR_PYTHON": "/nonexistent/python",
            "BCLI_ASR_MODEL": "/nonexistent/model",
        }
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError):
                asr.resolve("sensevoice")

    def test_unknown_engine_raises(self):
        from bilicli import asr

        with self.assertRaises(ValueError):
            asr.resolve("whisper-xl")


class TestFrames(unittest.TestCase):
    def test_merge_picks_across_timeline(self):
        import tempfile
        from pathlib import Path as P

        from bilicli import frames

        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i in range(6):
                p = P(d) / f"f{i}.jpg"
                p.write_bytes(b"x")
                paths.append(p)
            cands = [(i * 20.0, paths[i]) for i in range(6)]  # 0..100 秒
            picked = frames._merge(cands, duration=120.0, count=3)
            self.assertEqual(len(picked), 3)
            # 时间轴均匀分布：约 20 / 60 / 100 秒附近
            self.assertLess(picked[0][0], 30)
            self.assertGreater(picked[2][0], 90)
            # 未选中的文件应被删除
            self.assertEqual(len(list(P(d).glob("*.jpg"))), 3)


class TestAnonymousBuvid(unittest.TestCase):
    def test_buvid_fetched_once_and_cached(self):
        import json
        import os
        import tempfile
        from unittest import mock

        from bilicli import http

        calls = []

        def fake_open(self, url, headers, retries=None):
            calls.append(url)
            if "finger/spi" in url:
                return json.dumps({"data": {"b_3": "B3", "b_4": "B4"}}).encode()
            return b'{"code":0,"data":{}}'

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, {"BCLI_CONFIG_DIR": d}), \
             mock.patch.object(http.Client, "_open", fake_open):
            c = http.Client()
            c.get("/x/web-interface/view", {"bvid": "BV1"})
            self.assertEqual(c.cookies.get("buvid3"), "B3")
            self.assertEqual(c.cookies.get("buvid4"), "B4")
            c.get("/x/web-interface/view", {"bvid": "BV1"})
            self.assertEqual(len([u for u in calls if "finger/spi" in u]), 1)

    def test_logged_in_skips_buvid(self):
        from bilicli import http

        c = http.Client({"sessdata": "S"})
        c._ensure_buvid()
        self.assertNotIn("buvid3", c.cookies)


class TestMcp(unittest.TestCase):
    def test_initialize_and_tools(self):
        from bilicli import mcp

        tools = {t["name"]: t for t in mcp.build_tools()}
        init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, tools)
        self.assertEqual(init["result"]["serverInfo"]["name"], "bili")
        listing = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, tools)
        names = {t["name"] for t in listing["result"]["tools"]}
        self.assertIn("bili_hot", names)
        self.assertTrue(all("inputSchema" in t for t in listing["result"]["tools"]))

    def test_unknown_tool(self):
        from bilicli import mcp

        tools = {t["name"]: t for t in mcp.build_tools()}
        resp = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}}, tools)
        self.assertIn("error", resp)


class TestCliSurface(unittest.TestCase):
    def test_all_commands_registered(self):
        from bilicli.cli import build_parser

        parser = build_parser()
        actions = [a for a in parser._actions if a.dest == "command"]
        names = set(actions[0].choices)
        for expected in (
            "status", "whoami", "login", "logout", "search", "video", "user",
            "user-videos", "hot", "rank", "history", "favorites", "watch-later",
            "feed", "my-dynamics", "favorites-items", "like", "coin", "triple",
            "follow", "fav-add", "fav-remove", "comment", "audio", "asr", "asr-engines", "rcmd",
            "frames",
            "update", "api",
        ):
            self.assertIn(expected, names)

    def test_no_network_help(self):
        import contextlib
        import io

        from bilicli.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("bili", buf.getvalue())


class TestUpdate(unittest.TestCase):
    def test_parse_version(self):
        from bilicli.update import parse_version

        self.assertEqual(parse_version("v0.2.1"), (0, 2, 1))
        self.assertEqual(parse_version("0.10.0"), (0, 10, 0))
        self.assertEqual(parse_version("v1.0.0-rc1"), (1, 0, 1))

    def test_is_newer(self):
        from bilicli.update import is_newer

        self.assertTrue(is_newer("v0.2.1", "0.2.0"))
        self.assertFalse(is_newer("v0.2.0", "0.2.0"))
        self.assertFalse(is_newer("v0.1.9", "0.2.0"))

    def test_platform_asset_known(self):
        from bilicli import update

        with mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(update.platform_asset(), "bili-linux-x64")
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("platform.machine", return_value="arm64"):
            self.assertEqual(update.platform_asset(), "bili-macos-arm64")


class TestClientCookies(unittest.TestCase):
    def test_cookie_header_order_and_login_flag(self):
        c = Client({"sessdata": "s", "bili_jct": "j", "dedeuserid": "1"})
        self.assertTrue(c.logged_in)
        header = c.headers()["Cookie"]
        self.assertIn("SESSDATA=s", header)
        self.assertIn("DedeUserID=1", header)

    def test_anon(self):
        c = Client()
        self.assertFalse(c.logged_in)
        self.assertNotIn("Cookie", c.headers())


class TestGroqEngine(unittest.TestCase):
    def test_engine_registered(self):
        from bilicli import asr

        self.assertIn("groq", asr.ENGINES)
        self.assertTrue(asr.ENGINES["groq"]["remote"])
        self.assertEqual(asr.ALIASES["whisper"], "groq")

    def test_describe_without_key(self):
        from bilicli import asr

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            with mock.patch("bilicli.asr.config.get", return_value=None):
                info = asr.describe("groq")
        self.assertFalse(info["available"])
        self.assertIn("GROQ_API_KEY", info["reason"])

    def test_describe_with_key(self):
        from bilicli import asr

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}, clear=False):
            info = asr.describe("groq")
        self.assertTrue(info["available"])
        self.assertEqual(info["model"], "whisper-large-v3-turbo")

    def test_multipart_body(self):
        from bilicli import asr

        body, ctype = asr._multipart({"model": "whisper-large-v3-turbo"}, "file", b"abc", "a.mp3", "audio/mpeg")
        self.assertIn("multipart/form-data; boundary=", ctype)
        self.assertIn(b'name="model"', body)
        self.assertIn(b"whisper-large-v3-turbo", body)
        self.assertIn(b'filename="a.mp3"', body)
        self.assertTrue(body.endswith(b"--\r\n"))


if __name__ == "__main__":
    unittest.main()
