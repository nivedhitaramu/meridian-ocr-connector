"""Check the real Docker stack: Celery, Redis and PostgreSQL row-level security, with the mock model.

No sign-in is needed, because it seeds an API key directly in the database. CI runs this after `docker compose up`.
It proves a full check, that a killed worker recovers without duplicates (#19), intake grouping, a signed
webhook and retention. Uses only the standard library on the host.

    python scripts/ci_stack_check.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "http://localhost:8000"
SAMPLES = Path("samples")
TIMEOUT = 300
KEY = "mk_" + secrets.token_urlsafe(24)
SECRET = "whsec_" + secrets.token_urlsafe(24)
HOOK_FILE = "/tmp/hook.json"

SEED = """
import sys
from datetime import datetime, timedelta, timezone
from app.api.deps import hash_key
from app.db import models
from app.db.session import new_session
key, secret = sys.argv[1], sys.argv[2]
with new_session() as s:
    org = models.Organization(name="CI", retention_days=30)
    user = models.User(external_id="ci-stack-check", email="ci@example.com")
    s.add_all([org, user]); s.flush()
    s.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
    s.add(models.ApiKey(organization_id=org.id, name="ci", prefix=key[:10], key_hash=hash_key(key), created_by=user.id))
    s.add(models.WebhookEndpoint(organization_id=org.id, url="http://api:9100/hook", secret=secret))
    s.add(models.Shipment(organization_id=org.id, reference="OLD-SHIPMENT", created_at=datetime.now(timezone.utc) - timedelta(days=40)))
    s.commit()
"""

RECEIVER = """
import http.server, json
class Hook(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with open("%s", "a") as out:
            out.write(json.dumps({"signature": self.headers["X-Meridian-Signature"], "body": body.decode()}) + "\\n")
        self.send_response(204); self.end_headers()
    def log_message(self, *args): pass
http.server.HTTPServer(("0.0.0.0", 9100), Hook).serve_forever()
""" % HOOK_FILE

RETENTION = """
from app.worker.retention import apply_all
print(apply_all())
"""


def run(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=True).stdout


def compose_python(service: str, code: str, *args: str) -> str:
    return run("docker", "compose", "exec", "-T", service, "python", "-c", code, *args)


def request(method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> dict:
    wanted = {"X-API-Key": KEY, **(headers or {})}
    message = urllib.request.Request(API + path, data=body, method=method, headers=wanted)
    with urllib.request.urlopen(message, timeout=60) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def post_json(path: str, value: dict) -> dict:
    return request("POST", path, json.dumps(value).encode(), {"Content-Type": "application/json"})


def post_files(path: str, field: str, files: list[Path]) -> dict:
    boundary = uuid.uuid4().hex
    parts = b""
    for file in files:
        parts += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="upload"\r\n'
                  "Content-Type: application/octet-stream\r\n\r\n").encode() + file.read_bytes() + b"\r\n"
    parts += f"--{boundary}--\r\n".encode()
    return request("POST", path, parts, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def wait_for(description: str, condition, timeout: int = TIMEOUT, every: float = 1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(every)
    raise SystemExit(f"Timed out waiting for: {description}")


def submit(reference: str) -> tuple[str, str]:
    shipment = post_json("/v1/shipments", {"reference": reference})["id"]
    for name in ("S01_invoice.pdf", "S01_packing.pdf"):
        post_files(f"/v1/shipments/{shipment}/documents", "file", [SAMPLES / name])
    job = request("POST", f"/v1/shipments/{shipment}/jobs", headers={"Idempotency-Key": reference})["id"]
    return shipment, job


def job_state(job: str) -> dict:
    return request("GET", f"/v1/jobs/{job}")


def finished(job: str):
    state = job_state(job)
    return state if state["status"] in ("succeeded", "failed", "manual_review") else None


def check_full_flow() -> None:
    _, job = submit("CI-FLOW")
    state = wait_for("a job to finish through Celery", lambda: finished(job))
    assert state["status"] == "succeeded", state["status"]
    assert state["check"]["status"] == "Match", state["check"]
    assert state["config_version"] == "meridian-1", state["config_version"]
    print("OK  full check through Celery and Redis: Match")


def check_signed_webhook() -> None:
    def received():
        out = subprocess.run(["docker", "compose", "exec", "-T", "api", "cat", HOOK_FILE], text=True, capture_output=True)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
    line = wait_for("a webhook", received, timeout=60).splitlines()[0]
    hook = json.loads(line)
    parts = dict(item.split("=", 1) for item in hook["signature"].split(","))
    expected = hmac.new(SECRET.encode(), f"{parts['t']}.{hook['body']}".encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, parts["v1"]), "webhook signature didn't verify"
    assert json.loads(hook["body"])["check_status"] == "Match"
    print("OK  signed webhook delivered through Celery")


def check_worker_kill() -> None:
    _, job = submit("CI-KILL")
    wait_for("the job to start running", lambda: job_state(job)["status"] == "running", every=0.1)
    run("docker", "compose", "kill", "-s", "SIGKILL", "worker")
    print("    worker killed mid-job")
    state = job_state(job)
    assert state["status"] == "running", f"expected running after the kill, got {state['status']}"
    assert state["check"] is None
    run("docker", "compose", "up", "--detach", "worker")
    state = wait_for("the job to recover after the kill", lambda: finished(job))
    assert state["status"] == "succeeded", state["status"]
    assert state["attempts"] >= 2, f"expected a second attempt, got {state['attempts']}"
    assert state["check"]["status"] == "Match", state["check"]
    assert len(state["documents"]) == 2, f"expected 2 documents without duplicates, got {len(state['documents'])}"
    print(f"OK  killed worker recovered: attempts={state['attempts']}, one result, 2 documents")


def check_intake() -> None:
    post_files("/v1/intake", "files", [SAMPLES / "S02_invoice.pdf", SAMPLES / "S02_packing.pdf"])

    def grouped():
        items = request("GET", "/v1/intake")
        return items if items and all(item["status"] != "queued" for item in items) else None
    items = wait_for("intake to group a batch", grouped)
    assert [item["status"] for item in items] == ["grouped", "grouped"], items
    assert len({item["shipment_id"] for item in items}) == 1
    print("OK  intake grouped a pair into one shipment")


def check_retention() -> None:
    before = {row["reference"] for row in request("GET", "/v1/shipments")}
    assert "OLD-SHIPMENT" in before
    removed = compose_python("worker", RETENTION).strip()
    after = {row["reference"] for row in request("GET", "/v1/shipments")}
    assert removed == "1" and "OLD-SHIPMENT" not in after and "CI-FLOW" in after, (removed, after)
    print("OK  retention removed only the expired shipment, under row-level security")


def check_key_limits() -> None:
    try:
        request("GET", "/v1/audit-events")
    except urllib.error.HTTPError as error:
        assert error.code == 403, error.code
    else:
        raise SystemExit("An API key could read admin data")
    print("OK  an API key can't reach admin routes")


def main() -> None:
    compose_python("api", SEED, KEY, SECRET)
    subprocess.run(["docker", "compose", "exec", "--detach", "api", "python", "-c", RECEIVER], check=True)
    check_key_limits()
    check_full_flow()
    check_signed_webhook()
    check_worker_kill()
    check_intake()
    check_retention()
    print("All stack checks passed")


if __name__ == "__main__":
    sys.exit(main())
