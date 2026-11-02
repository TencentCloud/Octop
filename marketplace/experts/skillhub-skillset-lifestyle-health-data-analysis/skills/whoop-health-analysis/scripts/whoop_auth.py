#!/usr/bin/env python3
"""
Whoop OAuth 2.0 Authentication Handler

Usage:
    # First-time login (opens browser)
    python3 whoop_auth.py login --client-id ID --client-secret SECRET

    # Get current access token (auto-refreshes if expired)
    python3 whoop_auth.py token

    # Check auth status
    python3 whoop_auth.py status

    # Logout (delete stored tokens)
    python3 whoop_auth.py logout

Tokens are stored in ~/.clawdbot/whoop-tokens.json
"""

import argparse
import base64
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

TOKEN_FILE = os.path.expanduser("~/.clawdbot/whoop-tokens.json")
AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
USER_AGENT = "Clawdbot/1.0 (Whoop Integration)"
SCOPES = "offline read:recovery read:cycles read:workout read:sleep read:profile read:body_measurement"
REDIRECT_PORT = 9876
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


def save_tokens(data):
    """Save token data to file."""
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    data["saved_at"] = time.time()
    tmp_path = f"{TOKEN_FILE}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, TOKEN_FILE)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def load_tokens():
    """Load token data from file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def delete_tokens():
    """Delete stored tokens."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("Tokens deleted.")
    else:
        print("No tokens found.")


def is_expired(tokens):
    """Check if token is expired (with 5 min buffer)."""
    if not tokens:
        return True
    saved_at = tokens.get("saved_at", 0)
    expires_in = tokens.get("expires_in", 0)
    return time.time() > (saved_at + expires_in - 300)


def refresh_token(tokens):
    """Refresh the access token."""
    refresh = tokens.get("refresh_token")
    client_id = tokens.get("client_id")
    client_secret = tokens.get("client_secret")
    if not all([refresh, client_id, client_secret]):
        return None

    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            new_tokens = json.loads(resp.read())
        if "access_token" not in new_tokens:
            raise ValueError("No access_token in refresh response")
        new_tokens["client_id"] = client_id
        new_tokens["client_secret"] = client_secret
        save_tokens(new_tokens)
        return new_tokens
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
        print(f"Error refreshing token: {e}", file=sys.stderr)
        return None


def get_valid_token():
    """Get a valid access token, refreshing if needed."""
    tokens = load_tokens()
    if not tokens:
        print("Not authenticated. Run: whoop_auth.py login", file=sys.stderr)
        sys.exit(1)

    if is_expired(tokens):
        tokens = refresh_token(tokens)
        if not tokens:
            print("Token refresh failed. Run: whoop_auth.py login", file=sys.stderr)
            sys.exit(1)

    access_token = tokens.get("access_token")
    if not access_token:
        print("No access token found. Run: whoop_auth.py login", file=sys.stderr)
        sys.exit(1)
    return access_token


def do_login(client_id, client_secret):
    """Start OAuth login flow."""
    if not client_id or not client_secret:
        print("Client ID and Client Secret are required.", file=sys.stderr)
        sys.exit(1)

    auth_code_holder = {"code": None, "error": None, "state": None}
    done_event = threading.Event()
    expected_state = secrets.token_urlsafe(16)

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)
            state = params.get("state", [None])[0]
            if state != expected_state:
                auth_code_holder["error"] = "Invalid state"
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Error: invalid state</h2></body></html>")
                done_event.set()
                return

            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Authentication successful!</h2><p>You can close this tab.</p></body></html>")
                done_event.set()
                return

            error = params.get("error", ["Unknown error"])[0]
            auth_code_holder["error"] = error
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())
            done_event.set()

        def log_message(self, format, *args):
            pass  # Suppress logs

    try:
        server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    except OSError as e:
        print(f"Error starting local server on port {REDIRECT_PORT}: {e}", file=sys.stderr)
        sys.exit(1)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Build auth URL
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": expected_state,
    })
    auth_url = f"{AUTH_URL}?{params}"

    print(f"Opening browser for Whoop authorization...")
    print(f"If it doesn't open, visit: {auth_url}")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Wait for callback
    done_event.wait(timeout=180)
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=5)

    if auth_code_holder["error"]:
        print(f"Error during authorization: {auth_code_holder['error']}", file=sys.stderr)
        sys.exit(1)

    if not auth_code_holder["code"]:
        print("Error: No authorization code received.", file=sys.stderr)
        sys.exit(1)

    # Exchange code for token (client_secret_post method)
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": auth_code_holder["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            tokens = json.loads(resp.read())
        if "access_token" not in tokens:
            raise ValueError("No access_token in token response")
        tokens["client_id"] = client_id
        tokens["client_secret"] = client_secret
        save_tokens(tokens)
        print("Authentication successful! Tokens saved.")
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
        print(f"Error exchanging code for token: {e}", file=sys.stderr)
        sys.exit(1)


def do_status():
    """Show authentication status."""
    tokens = load_tokens()
    if not tokens:
        print("Status: Not authenticated")
        return

    expired = is_expired(tokens)
    print(f"Status: {'Expired' if expired else 'Active'}")
    print(f"Client ID: {tokens.get('client_id', 'N/A')[:8]}...")
    if not expired:
        remaining = (tokens.get("saved_at", 0) + tokens.get("expires_in", 0)) - time.time()
        print(f"Expires in: {int(remaining / 60)} minutes")
    print(f"Has refresh token: {'Yes' if tokens.get('refresh_token') else 'No'}")


def main():
    parser = argparse.ArgumentParser(description="Whoop OAuth Authentication")
    sub = parser.add_subparsers(dest="command")

    login_p = sub.add_parser("login", help="Start OAuth login flow")
    login_p.add_argument("--client-id", required=True)
    login_p.add_argument("--client-secret", required=True)

    sub.add_parser("token", help="Print current access token")
    sub.add_parser("status", help="Show auth status")
    sub.add_parser("logout", help="Delete stored tokens")

    args = parser.parse_args()

    if args.command == "login":
        do_login(args.client_id, args.client_secret)
    elif args.command == "token":
        print(get_valid_token())
    elif args.command == "status":
        do_status()
    elif args.command == "logout":
        delete_tokens()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
