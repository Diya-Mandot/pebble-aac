"""Dependency-free local dev server. Calls the real Lambda handler functions directly through a
synthetic API-Gateway-shaped event, so the code path matches what SAM/API Gateway will invoke later.
No third-party packages, no SAM CLI, no Docker required for this pass.

Run: python local_server.py [port]   (default port 8000)
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader (no python-dotenv dependency, per this file's dependency-free design).
    Only sets vars not already present in the environment, so a real shell export still wins."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler
from src.speak.app import lambda_handler as speak_handler
from src.profile.app import lambda_handler as profile_handler
from src.common.responses import CORS_HEADERS

ROUTES = {
    "/expand": expand_handler,
    "/simplify": simplify_handler,
    "/speak": speak_handler,
}

PROFILE_PATH_RE = re.compile(r"^/profile/(?P<id>[^/]+)$")


def _route(path, method):
    """Returns (handler, path_params) or (None, {}) if nothing matches. path_params mimics API
    Gateway's event["pathParameters"] shape for a proxied {id} path segment."""
    if method == "POST" and path in ROUTES:
        return ROUTES[path], {}
    match = PROFILE_PATH_RE.match(path)
    if match and method in ("GET", "POST"):
        return profile_handler, {"id": match.group("id")}
    return None, {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status_code: int, headers: dict, body: str):
        self.send_response(status_code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        # CORS preflight: the browser sends this before any cross-origin POST with a JSON body.
        self._send(204, CORS_HEADERS, "")

    def _dispatch(self, method):
        handler, path_params = _route(self.path, method)
        if handler is None:
            self._send(404, CORS_HEADERS, json.dumps({"error": "Not found"}))
            return

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length else ""

        event = {
            "httpMethod": method,
            "path": self.path,
            "body": raw_body or None,
            "pathParameters": path_params or None,
        }
        result = handler(event, None)

        self._send(result["statusCode"], result["headers"], result["body"])

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, format, *args):
        # Only method/path/status — never request bodies (icons, text, transcripts) or client
        # address. /profile/{id} embeds a dynamic, potentially-identifying id directly in the URL
        # path (unlike /expand, /simplify, /speak, whose paths are always the same static string),
        # and BaseHTTPRequestHandler's default log line includes the full raw request line
        # (self.requestline) -- redact the id segment so it never reaches logs, per PLAN.md's "no
        # ... profiles in logs" privacy rule.
        line = re.sub(r"(/profile/)[^\s?\"]+", r"\1<id>", format % args)
        sys.stderr.write(f"{line}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving /expand, /simplify, /speak, and /profile/{{id}} on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
