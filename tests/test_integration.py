"""Live integration tests — read-only commands against the real API.

They are skipped unless BILI_INTEGRATION=1 **and** a credential exists
(~/.config/bcli/credential.json or BCLI_SESSDATA). Write endpoints are never
touched here.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

CREDENTIAL = Path(os.environ.get("BCLI_CONFIG_DIR", Path.home() / ".config" / "bcli")) / "credential.json"
ENABLED = os.environ.get("BILI_INTEGRATION") == "1"
HAVE_AUTH = CREDENTIAL.exists() or bool(os.environ.get("BCLI_SESSDATA"))

BVID = "BV1xrnz6gEVD"
UID = "946974"


def run(*args: str) -> dict:
    proc = subprocess.run(["bili", *args], capture_output=True, text=True, timeout=120)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"bili {' '.join(args)} 输出不是 JSON: {proc.stdout[:200]} / {proc.stderr[:200]}")


@unittest.skipUnless(ENABLED, "设置 BILI_INTEGRATION=1 才跑联网测试")
class TestPublicReads(unittest.TestCase):
    def test_hot(self):
        payload = run("hot")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"])

    def test_search(self):
        payload = run("search", "影视飓风", "-n", "3")
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["data"]), 3)

    def test_video(self):
        payload = run("video", BVID)
        self.assertEqual(payload["data"]["bvid"], BVID)

    def test_user(self):
        payload = run("user", UID)
        self.assertEqual(payload["data"]["uid"], UID)

    def test_bad_bvid_shape(self):
        payload = run("video", "BV123")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_argument")


@unittest.skipUnless(ENABLED and HAVE_AUTH, "需要登录态")
class TestAccountReads(unittest.TestCase):
    def test_status(self):
        payload = run("status")
        self.assertTrue(payload["data"]["authenticated"])

    def test_history(self):
        self.assertTrue(run("history")["ok"])

    def test_favorites(self):
        self.assertTrue(run("favorites")["ok"])

    def test_watch_later(self):
        self.assertTrue(run("watch-later")["ok"])

    def test_feed(self):
        self.assertTrue(run("feed")["ok"])

    def test_update_check(self):
        payload = run("update", "--check")
        self.assertIn("latest", payload["data"])


if __name__ == "__main__":
    unittest.main()
