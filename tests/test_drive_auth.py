"""Tests for web/drive_auth.py, the helper that keeps the web app signed in to Google Drive."""

import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"))

import drive_auth  # noqa: E402

URL = "https://print.example.com"


def make_config(secret="s3cret"):
    return drive_auth.Config({"GOOGLE_CLIENT_SECRET": secret, "PUBLIC_URL": URL + "/"})


def set_cookies(response):
    """{name: (value, attributes)} from a response's Set-Cookie headers."""
    found = {}
    for name, value in response.headers:
        if name == "Set-Cookie":
            first, _, attrs = value.partition("; ")
            key, _, val = first.partition("=")
            found[key] = (val, attrs)
    return found


def header(response, wanted):
    return next(value for name, value in response.headers if name == wanted)


class FakeGoogle:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, fields):
        self.calls.append((url, fields))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class SealTests(unittest.TestCase):
    def test_round_trip(self):
        config = make_config()
        sealed = drive_auth.seal(config, {"r": "1//refresh-token"})
        self.assertNotIn("refresh", sealed)
        self.assertEqual(drive_auth.unseal(config, sealed), {"r": "1//refresh-token"})

    def test_tampered_or_foreign_cookie_is_refused(self):
        config = make_config()
        sealed = drive_auth.seal(config, {"r": "x"})
        flipped = sealed[:-3] + ("A" if sealed[-3] != "A" else "B") + sealed[-2:]
        self.assertIsNone(drive_auth.unseal(config, flipped))
        self.assertIsNone(drive_auth.unseal(make_config("other"), sealed))
        self.assertIsNone(drive_auth.unseal(config, ""))
        self.assertIsNone(drive_auth.unseal(config, "!!not base64!!"))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config()

    def request(self, method, target, cookies=None, origin=URL, google=None, now=1000.0):
        headers = {"Host": "print.example.com"}
        if origin:
            headers["Origin"] = origin
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return drive_auth.handle(self.config, method, target, headers, post=google or FakeGoogle([]), now=lambda: now)

    def sign_in(self, google_answer=None):
        start = self.request("GET", "/auth/start")
        state_cookie = set_cookies(start)[drive_auth.STATE_COOKIE][0]
        location = urllib.parse.urlsplit(header(start, "Location"))
        state = urllib.parse.parse_qs(location.query)["state"][0]
        google = FakeGoogle([google_answer or {"access_token": "a", "refresh_token": "1//r", "scope": drive_auth.SCOPE}])
        callback = self.request("GET", f"/auth/callback?code=c0de&state={state}",
                                cookies={drive_auth.STATE_COOKIE: state_cookie}, origin=None, google=google)
        return callback, google

    def test_off_without_secret(self):
        self.config = drive_auth.Config({})
        status = self.request("GET", "/auth/status")
        self.assertEqual(status.body, b'{"enabled": false, "signedIn": false}')
        self.assertEqual(self.request("GET", "/auth/start").status, 404)

    def test_start_asks_google_for_a_refresh_token(self):
        response = self.request("GET", "/auth/start?login_hint=me%40example.com")
        self.assertEqual(response.status, 302)
        location = urllib.parse.urlsplit(header(response, "Location"))
        query = urllib.parse.parse_qs(location.query)
        self.assertEqual(query["redirect_uri"], [URL + "/auth/callback"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["scope"], [drive_auth.SCOPE])
        self.assertEqual(query["login_hint"], ["me@example.com"])
        cookies = set_cookies(response)
        self.assertIn("HttpOnly", cookies[drive_auth.STATE_COOKIE][1])
        self.assertIn("Secure", cookies[drive_auth.STATE_COOKIE][1])
        self.assertIn("Max-Age=0", cookies[drive_auth.SESSION_COOKIE][1])

    def test_callback_keeps_the_refresh_token_in_a_sealed_cookie(self):
        callback, google = self.sign_in()
        self.assertEqual(callback.status, 200)
        self.assertIn(b'"ok": true', callback.body)
        fields = google.calls[0][1]
        self.assertEqual(fields["code"], "c0de")
        self.assertEqual(fields["grant_type"], "authorization_code")
        self.assertEqual(fields["client_secret"], "s3cret")
        session = set_cookies(callback)[drive_auth.SESSION_COOKIE][0]
        self.assertEqual(drive_auth.unseal(self.config, session), {"r": "1//r"})
        status = self.request("GET", "/auth/status", cookies={drive_auth.SESSION_COOKIE: session})
        self.assertIn(b'"signedIn": true', status.body)

    def test_callback_refuses_a_wrong_state(self):
        start = self.request("GET", "/auth/start")
        state_cookie = set_cookies(start)[drive_auth.STATE_COOKIE][0]
        google = FakeGoogle([])
        callback = self.request("GET", "/auth/callback?code=c&state=forged",
                                cookies={drive_auth.STATE_COOKIE: state_cookie}, google=google)
        self.assertIn(b'"ok": false', callback.body)
        self.assertNotIn(drive_auth.SESSION_COOKIE, set_cookies(callback))
        self.assertEqual(google.calls, [])

    def test_callback_without_refresh_token_fails(self):
        callback, _ = self.sign_in({"access_token": "a"})
        self.assertIn(b'"ok": false', callback.body)

    def test_token_uses_the_refresh_token(self):
        session = drive_auth.seal(self.config, {"r": "1//r"})
        google = FakeGoogle([{"access_token": "ya29.new", "expires_in": 3599}])
        response = self.request("POST", "/auth/token", cookies={drive_auth.SESSION_COOKIE: session}, google=google)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b'{"access_token": "ya29.new", "expires_in": 3599}')
        self.assertEqual(google.calls[0][1]["refresh_token"], "1//r")
        self.assertEqual(google.calls[0][1]["grant_type"], "refresh_token")

    def test_token_needs_the_apps_own_origin(self):
        session = drive_auth.seal(self.config, {"r": "1//r"})
        for origin in ("https://evil.example.com", None):
            response = self.request("POST", "/auth/token", cookies={drive_auth.SESSION_COOKIE: session}, origin=origin)
            self.assertEqual(response.status, 403)

    def test_revoked_refresh_token_signs_out(self):
        session = drive_auth.seal(self.config, {"r": "1//r"})
        google = FakeGoogle([drive_auth.GoogleError(400, "invalid_grant", "Token has been expired or revoked.")])
        response = self.request("POST", "/auth/token", cookies={drive_auth.SESSION_COOKIE: session}, google=google)
        self.assertEqual(response.status, 401)
        self.assertIn("Max-Age=0", set_cookies(response)[drive_auth.SESSION_COOKIE][1])

    def test_google_down_keeps_the_sign_in(self):
        session = drive_auth.seal(self.config, {"r": "1//r"})
        google = FakeGoogle([drive_auth.GoogleError(502, "unreachable", "Could not reach Google")])
        response = self.request("POST", "/auth/token", cookies={drive_auth.SESSION_COOKIE: session}, google=google)
        self.assertEqual(response.status, 502)
        self.assertNotIn(drive_auth.SESSION_COOKIE, set_cookies(response))

    def test_token_without_sign_in(self):
        self.assertEqual(self.request("POST", "/auth/token").status, 401)

    def test_sign_out_revokes_and_clears(self):
        session = drive_auth.seal(self.config, {"r": "1//r"})
        google = FakeGoogle([{}])
        response = self.request("POST", "/auth/signout", cookies={drive_auth.SESSION_COOKIE: session}, google=google)
        self.assertEqual(response.status, 200)
        self.assertEqual(google.calls, [(drive_auth.REVOKE_URL, {"token": "1//r"})])
        self.assertIn("Max-Age=0", set_cookies(response)[drive_auth.SESSION_COOKIE][1])

    def test_address_from_the_proxy_headers(self):
        config = drive_auth.Config({"GOOGLE_CLIENT_SECRET": "x"})
        headers = {"Host": "internal:8080", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "print.example.com"}
        self.assertEqual(drive_auth.base_url(config, headers), URL)
        self.assertEqual(drive_auth.base_url(config, {"Host": "localhost:8000"}), "http://localhost:8000")


if __name__ == "__main__":
    unittest.main()
