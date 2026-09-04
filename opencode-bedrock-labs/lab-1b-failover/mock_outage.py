#!/usr/bin/env python3
"""A fake Bedrock endpoint that fails, so you can simulate a provider outage.

Modes:
  throttle      429 ThrottlingException  (rate limited - the realistic incident)
  server-error  503 ServiceUnavailable   (provider down)
  client-error  400 ValidationException  (OUR bug - failover must NOT fire)
  timeout       accepts the connection, never responds (client must give up)

Usage: python3 mock_outage.py [throttle|server-error|client-error|timeout] [port]
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MODES = {
    # (http status, Bedrock exception name, message)
    "throttle":     (429, "ThrottlingException",
                     "Too many requests, please wait before trying again."),
    "server-error": (503, "ServiceUnavailableException",
                     "The service is temporarily unavailable."),
    # A 400 is OUR bug, not the provider's. The router must NOT fail over on it.
    "client-error": (400, "ValidationException",
                     "The provided model identifier is invalid."),
    "timeout":      (0,   "", ""),
}

mode = sys.argv[1] if len(sys.argv) > 1 else "throttle"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8099
if mode not in MODES:
    print(f"unknown mode {mode!r}; pick one of {list(MODES)}", file=sys.stderr)
    raise SystemExit(2)
status, err_type, message = MODES[mode]


class Handler(BaseHTTPRequestHandler):
    def _respond(self):
        if mode == "timeout":
            print(f"HANG {self.command} {self.path}", flush=True)
            time.sleep(600)          # never answer; the client must time out
            return
        body = json.dumps({"__type": err_type, "message": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f"HIT {self.command} {self.path} -> {status} {err_type}", flush=True)

    do_GET = do_POST = do_PUT = _respond

    def log_message(self, *args):
        pass                          # keep our own log clean


if __name__ == "__main__":
    print(f"mock outage endpoint listening on 127.0.0.1:{port} mode={mode}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
