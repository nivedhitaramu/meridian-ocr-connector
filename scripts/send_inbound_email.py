"""Post an .eml file to the mailbox route the way an email provider would, signed with INBOUND_EMAIL_SECRET.

    python scripts/send_inbound_email.py samples/packet_S02_match.eml --to inbox+<token>@<domain> --from clerk@example.com

For local testing, and as the reference for a provider adapter (see docs/MAILBOX.md). It replaces the To and From
headers so a sample packet reaches your mailbox.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path

import httpx


def sign(secret: str, body: bytes, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def rewrite(raw: bytes, to: str, sender: str) -> bytes:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    for header, value in (("To", to), ("From", sender)):
        del message[header]
        message[header] = value
    return message.as_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eml", type=Path)
    parser.add_argument("--to", required=True)
    parser.add_argument("--from", dest="sender", required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    secret = os.environ.get("INBOUND_EMAIL_SECRET")
    if not secret:
        print("Set INBOUND_EMAIL_SECRET first.")
        return 2
    body = rewrite(args.eml.read_bytes(), args.to, args.sender)
    response = httpx.post(f"{args.api}/v1/inbound/email", content=body, timeout=60,
                          headers={"Content-Type": "message/rfc822", "X-Meridian-Inbound-Signature": sign(secret, body)})
    print(response.status_code, response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
