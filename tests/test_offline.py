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
            "follow", "fav-add", "fav-remove", "comment", "audio", "asr",
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


if __name__ == "__main__":
    unittest.main()
