"""Serve live invite stats on the local network."""

from __future__ import annotations

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "invite_status.json"
HOST = "0.0.0.0"
PORT = 8765


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def read_status() -> dict:
    if not STATUS_FILE.exists():
        return {
            "updated_at": "",
            "state": "waiting",
            "today_successful": 0,
            "total_invited": 0,
            "session_successful": 0,
            "source_subreddit": "",
            "lan_hint": local_lan_ip(),
        }
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "state": f"status-read-error: {exc}",
            "today_successful": 0,
            "total_invited": 0,
            "session_successful": 0,
            "source_subreddit": "",
            "lan_hint": local_lan_ip(),
        }


class StatusHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict):
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, payload: dict):
        html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta http-equiv=\"refresh\" content=\"5\">
  <title>Invite Status</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Georgia, serif; margin: 2rem; background: #f7f2e8; color: #1f1a14; }}
    .card {{ max-width: 42rem; padding: 1.5rem 1.75rem; background: #fffaf0; border: 1px solid #d9c9aa; border-radius: 14px; box-shadow: 0 10px 30px rgba(80, 58, 24, 0.08); }}
    h1 {{ margin-top: 0; font-size: 1.8rem; }}
    .stat {{ font-size: 2rem; font-weight: 700; margin: 0.25rem 0 1rem; }}
    .label {{ font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.08em; color: #7a6240; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 1rem; margin: 1rem 0; }}
    .panel {{ padding: 1rem; background: #f4ead7; border-radius: 10px; }}
    code {{ font-size: 0.95rem; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Reddit Inviter Status</h1>
    <div class=\"grid\">
      <div class=\"panel\"><div class=\"label\">Today's Successful Invites</div><div class=\"stat\">{payload.get('today_successful', 0)}</div></div>
      <div class=\"panel\"><div class=\"label\">Total Invited</div><div class=\"stat\">{payload.get('total_invited', 0)}</div></div>
      <div class=\"panel\"><div class=\"label\">This Session</div><div class=\"stat\">{payload.get('session_successful', 0)}</div></div>
    </div>
    <p><strong>State:</strong> {payload.get('state', '')}</p>
    <p><strong>Source subreddit:</strong> {payload.get('source_subreddit', '') or 'n/a'}</p>
    <p><strong>Updated:</strong> {payload.get('updated_at', '') or 'n/a'}</p>
    <p><strong>JSON endpoint:</strong> <code>/status.json</code></p>
  </div>
</body>
</html>
"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        payload = read_status()
        if self.path == "/status.json":
            self._send_json(payload)
            return
        self._send_html(payload)

    def log_message(self, format: str, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), StatusHandler)
    ip = local_lan_ip()
    print(f"LAN status server listening on http://{ip}:{PORT} and http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()