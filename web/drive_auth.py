#!/usr/bin/env python3
"""
Keeps Cube Labeler web signed in to Google Drive.

Without it, Google hands the page a token that works for an hour, and then the user has to
click Continue. With it, the user signs in once per device: Google gives this helper a
refresh token, which it keeps encrypted in a cookie on the user's own browser, and the page
asks it for a new one-hour token whenever it needs one. The helper keeps nothing itself, so
it needs no database or volume, and any number of people can sign in.

The Docker image runs it beside nginx, which passes /auth/ to it:

    GOOGLE_CLIENT_SECRET=...  PUBLIC_URL=https://print.tobezone.com  python3 drive_auth.py

GOOGLE_CLIENT_SECRET   the OAuth client's secret, from Google Cloud Console (required;
                       without it the helper answers that it is off, and the page signs
                       in the hourly way)
GOOGLE_CLIENT_ID       the OAuth client ID (default: the one in web/js/gdrive.js)
PUBLIC_URL             the address people open the app at; Google sends them back to
                       PUBLIC_URL/auth/callback (default: worked out from the request)
DRIVE_AUTH_PORT        the port to listen on, on 127.0.0.1 only (default 8081)

Only the standard library is used, so the image needs nothing but python3.
"""

import base64
import hashlib
import hmac
import html
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_CLIENT_ID = "883752261996-i1id09p1b49p304st8h3d7kdcpaps5c5.apps.googleusercontent.com"
SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SESSION_COOKIE = "cube_drive"
STATE_COOKIE = "cube_drive_state"
# Chrome keeps a cookie for at most 400 days; it is renewed every time a token is handed out
SESSION_AGE = 400 * 24 * 3600
STATE_AGE = 15 * 60
# The page and the sign-in window find each other on this channel (see web/js/gdrive.js)
CHANNEL = "cube-drive-sign-in"


class Config:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.client_id = env.get("GOOGLE_CLIENT_ID", "").strip() or DEFAULT_CLIENT_ID
        self.client_secret = env.get("GOOGLE_CLIENT_SECRET", "").strip()
        self.public_url = env.get("PUBLIC_URL", "").strip().rstrip("/")
        self.port = int(env.get("DRIVE_AUTH_PORT", "") or 8081)
        # The cookie keys come from the secret, so they survive a restart without more setup;
        # a new secret signs everyone out, which is what you want after replacing it
        root = hmac.new(self.client_secret.encode(), b"cube-labeler drive cookie", hashlib.sha256).digest()
        self.enc_key = hmac.new(root, b"encrypt", hashlib.sha256).digest()
        self.mac_key = hmac.new(root, b"sign", hashlib.sha256).digest()

    @property
    def enabled(self):
        return bool(self.client_secret)


# --- Sealed cookies -------------------------------------------------------------------------
# Encrypt-then-MAC with HMAC-SHA256 only: HMAC as a stream cipher in counter mode, then an
# HMAC tag over nonce and ciphertext. The standard library has no AES, and this is just as sound.

def _keystream(key, nonce, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def seal(config, data):
    plain = json.dumps(data, separators=(",", ":")).encode()
    nonce = secrets.token_bytes(16)
    cipher = bytes(a ^ b for a, b in zip(plain, _keystream(config.enc_key, nonce, len(plain))))
    tag = hmac.new(config.mac_key, nonce + cipher, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + cipher + tag).decode().rstrip("=")


def unseal(config, value):
    """The data in a sealed cookie, or None if it was changed, made with another key or garbled."""
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return None
    if len(raw) < 33:
        return None
    nonce, cipher, tag = raw[:16], raw[16:-16], raw[-16:]
    if not hmac.compare_digest(tag, hmac.new(config.mac_key, nonce + cipher, hashlib.sha256).digest()[:16]):
        return None
    plain = bytes(a ^ b for a, b in zip(cipher, _keystream(config.enc_key, nonce, len(cipher))))
    try:
        return json.loads(plain)
    except ValueError:
        return None


# --- Talking to Google ----------------------------------------------------------------------

class GoogleError(Exception):
    def __init__(self, status, error, description=""):
        super().__init__(description or error)
        self.status = status
        self.error = error
        self.description = description


def post_form(url, fields):
    """POSTs a form to Google and returns the JSON answer; raises GoogleError when it says no."""
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            text = response.read()
            return json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            answer = json.loads(e.read())
        except ValueError:
            answer = {}
        raise GoogleError(e.code, answer.get("error", "http_error"), answer.get("error_description", "")) from None
    except (urllib.error.URLError, OSError) as e:
        raise GoogleError(502, "unreachable", f"Could not reach Google: {e}") from None


# --- Requests -------------------------------------------------------------------------------

class Response:
    def __init__(self, status=200, body=b"", content_type="application/json", headers=None):
        self.status = status
        self.body = body if isinstance(body, bytes) else body.encode()
        self.headers = [("Content-Type", content_type), ("Cache-Control", "no-store")] + list(headers or [])


def json_response(data, status=200, headers=None):
    return Response(status, json.dumps(data), headers=headers)


def base_url(config, headers):
    """The app's address: PUBLIC_URL, or what the reverse proxy and nginx say it is."""
    if config.public_url:
        return config.public_url
    proto = (headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip()
    host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "localhost").split(",")[0].strip()
    return f"{proto}://{host}"


def cookie(name, value, url, max_age):
    parts = [f"{name}={value}", "Path=/auth", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if url.startswith("https://"):
        parts.append("Secure")
    return ("Set-Cookie", "; ".join(parts))


def read_cookies(headers):
    jar = {}
    for part in (headers.get("Cookie") or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name:
            jar[name] = value
    return jar


def same_origin(headers, url):
    """True when a POST comes from the app's own page. Browsers always send Origin on a POST
    made with fetch, so another site cannot ask for a token with the user's cookie."""
    origin = headers.get("Origin")
    return origin is not None and origin.rstrip("/") == url


def window_page(url, ok, error=""):
    """The page the sign-in window lands on: it tells the app how it went and closes itself."""
    message = json.dumps({"ok": ok, "error": error}).replace("<", "\\u003c")
    title = "Signed in" if ok else "Sign-in failed"
    text = ("You are signed in to Google Drive. You can close this window and go back to Cube Labeler."
            if ok else f"Google sign-in did not work: {html.escape(error)}")
    return Response(200, f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Cube Labeler</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f4f5f7; color: #1f2430; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #1f2430; color: #e8eaf0; }} a {{ color: #8ab4ff; }} }}
  main {{ max-width: 26rem; padding: 1.5rem; text-align: center; }}
</style></head>
<body><main><h1>{title}</h1><p>{text}</p><p><a href="{html.escape(url)}/#settings">Open Cube Labeler</a></p></main>
<script>
  try {{ const c = new BroadcastChannel({json.dumps(CHANNEL)}); c.postMessage({message}); c.close(); }} catch (e) {{}}
  setTimeout(() => window.close(), {600 if ok else 4000});
</script></body></html>""", content_type="text/html; charset=utf-8",
                    headers=[("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")])


def handle(config, method, target, headers, post=post_form, now=time.time):
    """Answers one request to /auth/...; `headers` is a dict-like with the request headers."""
    parsed = urllib.parse.urlsplit(target)
    path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
    url = base_url(config, headers)
    jar = read_cookies(headers)
    session = unseal(config, jar.get(SESSION_COOKIE, "")) if config.enabled else None

    if path == "/auth/status" and method == "GET":
        return json_response({"enabled": config.enabled, "signedIn": bool(session and session.get("r"))})

    if not config.enabled:
        return json_response({"error": "off", "message": "Google sign-in is not set up on this server."}, 404)

    if path == "/auth/start" and method == "GET":
        state = secrets.token_urlsafe(24)
        params = {
            "client_id": config.client_id,
            "redirect_uri": f"{url}/auth/callback",
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            # consent makes Google hand out a refresh token every time, also on a second device
            "prompt": "select_account consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        hint = (query.get("login_hint") or [""])[0]
        if hint:
            params["login_hint"] = hint
        return Response(302, headers=[
            ("Location", f"{AUTH_URL}?{urllib.parse.urlencode(params)}"),
            cookie(STATE_COOKIE, seal(config, {"s": state, "t": int(now())}), url, STATE_AGE),
            # Signing in again replaces the old sign-in, also when it is with another account
            cookie(SESSION_COOKIE, "", url, 0),
        ])

    if path == "/auth/callback" and method == "GET":
        clear_state = cookie(STATE_COOKIE, "", url, 0)
        expected = unseal(config, jar.get(STATE_COOKIE, ""))
        state = (query.get("state") or [""])[0]
        if not expected or not state or not hmac.compare_digest(expected.get("s", ""), state) \
                or now() - expected.get("t", 0) > STATE_AGE:
            response = window_page(url, False, "The sign-in took too long or came from somewhere else. Try again.")
        elif "error" in query:
            error = query["error"][0]
            response = window_page(url, False, "Sign-in was cancelled." if error == "access_denied" else error)
        else:
            try:
                tokens = post(TOKEN_URL, {
                    "code": (query.get("code") or [""])[0],
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "redirect_uri": f"{url}/auth/callback",
                    "grant_type": "authorization_code",
                })
            except GoogleError as e:
                response = window_page(url, False, e.description or e.error)
            else:
                if not tokens.get("refresh_token"):
                    response = window_page(url, False, "Google did not allow staying signed in. Try again.")
                elif SCOPE not in tokens.get("scope", SCOPE).split():
                    response = window_page(url, False, "Allow Cube Labeler to use its files in your Drive, or sync can't work.")
                else:
                    response = window_page(url, True)
                    response.headers.append(cookie(SESSION_COOKIE, seal(config, {"r": tokens["refresh_token"]}), url, SESSION_AGE))
        response.headers.append(clear_state)
        return response

    if path == "/auth/token" and method == "POST":
        if not same_origin(headers, url):
            return json_response({"error": "origin"}, 403)
        if not session or not session.get("r"):
            return json_response({"error": "signed_out"}, 401)
        try:
            tokens = post(TOKEN_URL, {
                "refresh_token": session["r"],
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "grant_type": "refresh_token",
            })
        except GoogleError as e:
            if e.error in ("invalid_grant", "unauthorized_client"):
                # Revoked, expired or from another client: the user has to sign in again
                return json_response({"error": "signed_out"}, 401, [cookie(SESSION_COOKIE, "", url, 0)])
            return json_response({"error": "google", "message": e.description or e.error}, 502)
        # Google may hand out a new refresh token; keep whichever is newest
        sealed = seal(config, {"r": tokens.get("refresh_token") or session["r"]})
        return json_response({"access_token": tokens["access_token"], "expires_in": int(tokens.get("expires_in", 3600))},
                             headers=[cookie(SESSION_COOKIE, sealed, url, SESSION_AGE)])

    if path == "/auth/signout" and method == "POST":
        if not same_origin(headers, url):
            return json_response({"error": "origin"}, 403)
        # Google takes revoking as removing the app from the account, which signs out every
        # device, so only "everywhere" does it; otherwise only this browser forgets the sign-in
        everywhere = (query.get("everywhere") or [""])[0] == "1"
        if everywhere and session and session.get("r"):
            try:
                post(REVOKE_URL, {"token": session["r"]})
            except GoogleError:
                pass  # signed out here anyway; the user can remove the app in their Google account
        return json_response({"ok": True}, headers=[cookie(SESSION_COOKIE, "", url, 0)])

    return json_response({"error": "not_found"}, 404)


class Handler(http.server.BaseHTTPRequestHandler):
    config = None
    server_version = "CubeLabelerAuth"

    def _answer(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(min(length, 65536))  # nothing is read from the body
        response = handle(self.config, method, self.path, self.headers)
        self.send_response(response.status)
        for name, value in response.headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self):
        self._answer("GET")

    def do_POST(self):
        self._answer("POST")

    def log_message(self, fmt, *args):
        # The query string holds Google's one-time code, so only the path is logged
        sys.stderr.write(f"drive-auth: {self.command} {urllib.parse.urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")


def main():
    config = Config()
    Handler.config = config
    server = http.server.ThreadingHTTPServer(("127.0.0.1", config.port), Handler)
    state = "on" if config.enabled else "off (GOOGLE_CLIENT_SECRET is not set, so the page signs in the hourly way)"
    print(f"drive-auth: listening on 127.0.0.1:{config.port}, staying signed in to Google Drive is {state}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
