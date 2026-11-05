"""An external script: submit a shipment with an API key, then check the signed webhook it receives.

    python scripts/customer_example.py --api https://api.example.com --key mk_... --secret whsec_... \\
        --port 9000 samples/S01_invoice.pdf samples/S01_packing.pdf

The address you registered as a webhook must reach --port on this computer. Uses synthetic documents only.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import json
import time
import uuid

import httpx

MAX_AGE_SECONDS = 300


def verify(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    """Check the signature and refuse an old timestamp, so a captured request can't be replayed."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((time.time() if now is None else now) - timestamp) > MAX_AGE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("--api", "--key", "--secret"):
        parser.add_argument(name, required=True)
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.api, headers={"X-API-Key": args.key}, timeout=60)
    shipment = client.post("/v1/shipments", json={"reference": f"API-{uuid.uuid4().hex[:8]}"}).raise_for_status().json()
    for path in args.files:
        with open(path, "rb") as file:
            client.post(f"/v1/shipments/{shipment['id']}/documents", files={"file": ("upload", file)}).raise_for_status()
    job = client.post(f"/v1/shipments/{shipment['id']}/jobs", headers={"Idempotency-Key": uuid.uuid4().hex}).raise_for_status().json()
    print("Started job", job["id"])

    class Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            valid = verify(args.secret, self.headers.get("X-Meridian-Signature", ""), body)
            self.send_response(204 if valid else 401)
            self.end_headers()
            if valid:
                print("Signed result:", json.loads(body))
                self.server.done = True

    server = http.server.HTTPServer(("0.0.0.0", args.port), Receiver)
    server.done = False
    while not server.done:
        server.handle_request()


if __name__ == "__main__":
    main()
