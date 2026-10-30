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
