"""Dependency-free local dev server. Calls the real Lambda handler functions directly through a
synthetic API-Gateway-shaped event, so the code path matches what SAM/API Gateway will invoke later.
No third-party packages, no SAM CLI, no Docker required for this pass.

Run: python local_server.py [port]   (default port 8000)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler
from src.common.responses import CORS_HEADERS

ROUTES = {
    "/expand": expand_handler,
    "/simplify": simplify_handler,
}


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

    def do_POST(self):
        handler = ROUTES.get(self.path)
        if handler is None:
            self._send(404, CORS_HEADERS, json.dumps({"error": "Not found"}))
            return

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length else ""

        event = {"httpMethod": "POST", "path": self.path, "body": raw_body}
        result = handler(event, None)

        self._send(result["statusCode"], result["headers"], result["body"])

    def log_message(self, format, *args):
        # Only method/path/status — never request bodies (icons, text, transcripts, profile ids)
        # or client address.
        sys.stderr.write(f"{format % args}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving /expand and /simplify on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
