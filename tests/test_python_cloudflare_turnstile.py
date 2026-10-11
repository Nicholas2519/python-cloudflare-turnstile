"""Unit tests for python_cloudflare_turnstile - standard library only."""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import python_cloudflare_turnstile as mod  # noqa: E402

PAGE = '<div class="cf-turnstile" data-sitekey="0xSITE" data-action="checkout"></div>'


def ok_body(token="0.TOKEN"):
    return {"success": True, "data": {"token": token}}


class FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestReadPage(unittest.TestCase):
    def test_returns_decoded_html(self):
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(b"<html>hi</html>")):
            self.assertEqual(mod.read_page("https://example.com/"), "<html>hi</html>")


class TestSitekeyDiscovery(unittest.TestCase):
    def test_sitekey_from_markup(self):
        self.assertEqual(mod.find_sitekey("https://example.com/", PAGE), "0xSITE")

    def test_js_style_sitekey(self):
        html = '<script>sitekey: "0xJSKEY"</script>'
        self.assertEqual(mod.find_sitekey("https://example.com/", html), "0xJSKEY")

    def test_missing_sitekey_raises(self):
        with self.assertRaises(mod.TurnstileTokenError):
            mod.find_sitekey("https://example.com/", "<html></html>")

    def test_find_action(self):
        self.assertEqual(mod.find_action(PAGE), "checkout")
        self.assertIsNone(mod.find_action("<html></html>"))


class TestPayload(unittest.TestCase):
    def test_minimal_payload(self):
        p = mod.build_payload("0xSITE", "https://example.com/")
        self.assertEqual(p["task_type"], "turnstiletask")
        self.assertEqual(p["sitekey"], "0xSITE")
        self.assertNotIn("proxy", p)
        self.assertNotIn("action", p)
        self.assertNotIn("cdata", p)

    def test_optional_fields(self):
        p = mod.build_payload("0xSITE", "https://example.com/",
                              proxy="http://u:p@1.2.3.4:8080",
                              action="checkout", cdata="cart-1")
        self.assertEqual(p["proxy"], "http://u:p@1.2.3.4:8080")
        self.assertEqual(p["action"], "checkout")
        self.assertEqual(p["cdata"], "cart-1")


class TestCreateToken(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with self.assertRaises(mod.TurnstileTokenError):
            mod.create_token("", "0xSITE", "https://example.com/")

    def test_success_returns_token_result(self):
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(ok_body())):
            result = mod.create_token("pk_x", "0xSITE", "https://example.com/")
        self.assertEqual(result.token, "0.TOKEN")
        self.assertEqual(result.sitekey, "0xSITE")
        self.assertTrue(result.raw["success"])

    def test_api_error_raises(self):
        body = {"success": False, "error": "unsolvable"}
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(body)):
            with self.assertRaises(mod.TurnstileTokenError):
                mod.create_token("pk_x", "0xSITE", "https://example.com/")

    def test_missing_token_raises(self):
        body = {"success": True, "data": {}}
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(body)):
            with self.assertRaises(mod.TurnstileTokenError):
                mod.create_token("pk_x", "0xSITE", "https://example.com/")

    def test_retry_then_success(self):
        side_effect = [OSError("boom"), FakeResponse(ok_body())]
        with mock.patch.object(mod, "urlopen", side_effect=side_effect):
            with mock.patch.object(mod.time, "sleep") as sleeper:
                result = mod.create_token("pk_x", "0xSITE", "https://example.com/", retries=2)
        self.assertEqual(result.token, "0.TOKEN")
        sleeper.assert_called_once()


class TestTokenForPage(unittest.TestCase):
    def test_discovers_sitekey_and_forwards_action(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse(ok_body())

        with mock.patch.object(mod, "urlopen", side_effect=fake_urlopen):
            result = mod.token_for_page("pk_x", "https://example.com/", html=PAGE)
        self.assertEqual(result.token, "0.TOKEN")
        self.assertEqual(captured["body"]["sitekey"], "0xSITE")
        self.assertEqual(captured["body"]["action"], "checkout")


if __name__ == "__main__":
    unittest.main()
