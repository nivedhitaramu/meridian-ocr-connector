"""A stand-in warehouse system that receives verified goods receipts, for trying the WMS connector.

    python scripts/sandbox_wms.py --secret whsec_... [--port 8765]

It checks each request's signature, refuses old or tampered ones, and prints what a real WMS would book in.
Nothing is stored. Run the API with WEBHOOK_ALLOW_PRIVATE=1 so it may deliver to localhost.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_AGE_SECONDS = 300


def verify(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((time.time() if now is None else now) - timestamp) > MAX_AGE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def serve(secret: str, port: int, received: list | None = None) -> ThreadingHTTPServer:
    """Starts in the background and returns the server. Accepted receipts are appended to `received`."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if not verify(secret, self.headers.get("X-Meridian-Signature", ""), body):
                self.send_response(401)
                self.end_headers()
                return
            receipt = json.loads(body)
            if received is not None:
                received.append(receipt)
            else:
                v = receipt.get("verification", {})
                print(f"booked {receipt.get('reference')} | {v.get('status')} by {v.get('decided_by')} | "
                      f"{len(receipt.get('documents', []))} documents")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):  # keep the output to what was booked
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.secret, args.port)
    print(f"sandbox WMS listening on http://127.0.0.1:{args.port}/receipts")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
