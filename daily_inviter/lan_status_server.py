"""Serve live invite stats on the local network."""

from __future__ import annotations

import json
import re
import socket
import sys
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from console_output import configure_utf8_output


configure_utf8_output()

BASE_DIR = Path(__file__).resolve().parent
TALLY_FILE = BASE_DIR / "daily_invite_tally.txt"
HOST = "0.0.0.0"
PORT = 8765


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def read_daily_tallies() -> dict[str, tuple[int, int]]:
    tallies: dict[str, tuple[int, int]] = {}

    if not TALLY_FILE.exists():
        return tallies

    try:
        for raw_line in TALLY_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = re.fullmatch(
                r"(\d{4}-\d{2}-\d{2})\s+processed=(\d+)\s+successful=(\d+)",
                line,
            )
            if not match:
                continue

            tally_date, processed_count, successful_count = match.groups()
            existing_processed, existing_successful = tallies.get(tally_date, (0, 0))
            tallies[tally_date] = (
                existing_processed + int(processed_count),
                existing_successful + int(successful_count),
            )
    except Exception as exc:
        raise RuntimeError(f"tally-read-error: {exc}") from exc

    return tallies


def read_status() -> dict:
    try:
        tallies = read_daily_tallies()
    except RuntimeError as exc:
        return {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "state": str(exc),
            "today_processed": 0,
            "today_successful": 0,
            "daily_totals": [],
            "lan_hint": local_lan_ip(),
        }

    today = date.today().isoformat()
    today_processed, today_successful = tallies.get(today, (0, 0))
    total_processed = sum(processed_count for processed_count, _ in tallies.values())
    total_successful = sum(successful_count for _, successful_count in tallies.values())
    updated_at = ""
    if TALLY_FILE.exists():
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(TALLY_FILE.stat().st_mtime))

    return {
        "updated_at": updated_at,
        "state": "ready" if tallies else "waiting",
        "today_processed": today_processed,
        "today_successful": today_successful,
        "total_processed": total_processed,
        "total_successful": total_successful,
        "daily_totals": [
            {
                "date": tally_date,
                "processed": processed_count,
                "successful": successful_count,
            }
            for tally_date, (processed_count, successful_count) in sorted(tallies.items())
        ],
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
        <h1>reddit-android-bot Status</h1>
    <div class=\"grid\">
                        <div class="panel"><div class="label">Today's Processed</div><div class="stat">{payload.get('today_processed', 0)}</div></div>
                        <div class="panel"><div class="label">Today's Successful</div><div class="stat">{payload.get('today_successful', 0)}</div></div>
                        <div class="panel"><div class="label">Total Processed</div><div class="stat">{payload.get('total_processed', 0)}</div></div>
                        <div class="panel"><div class="label">Total Successful</div><div class="stat">{payload.get('total_successful', 0)}</div></div>
    </div>
    <p><strong>State:</strong> {payload.get('state', '')}</p>
    <p><strong>Updated:</strong> {payload.get('updated_at', '') or 'n/a'}</p>
    <p><strong>JSON endpoint:</strong> <code>/status.json</code></p>
                <pre>{json.dumps(payload.get('daily_totals', []), indent=2)}</pre>
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
