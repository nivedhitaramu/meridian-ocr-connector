"""A local stand-in for Clerk's token service, for browser tests only. Its key is new on every start."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "http://127.0.0.1:9199"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "e2e", "use": "sig", "alg": "RS256"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/.well-known/jwks.json":
            return self._send(json.dumps({"keys": [JWK]}).encode())
        user = parse_qs(url.query).get("user", ["alice"])[0]
        now = int(time.time())
        token = jwt.encode({"iss": ISSUER, "sub": f"user_{user}", "email": f"{user}@example.com", "iat": now, "exp": now + 600,
                            "sid": f"sess_{user}"}, KEY, algorithm="RS256", headers={"kid": "e2e"})
        self._send(json.dumps({"token": token}).encode())

    def log_message(self, *_):
        pass


ThreadingHTTPServer(("127.0.0.1", 9199), Handler).serve_forever()
