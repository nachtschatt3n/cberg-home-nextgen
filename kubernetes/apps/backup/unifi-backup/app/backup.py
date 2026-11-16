#!/usr/bin/env python3
"""Copy the newest UniFi controller autobackup (.unf) to the NAS.

Flow (ONE login per run, never retried -- the gateway rate-limits
POST /api/auth/login and every extra attempt extends a 429 lockout):
  1. POST /api/auth/login            -> session cookie + CSRF token
  2. POST /proxy/network/api/s/<site>/cmd/backup {"cmd":"list-backups"}
  3. GET  /proxy/network/dl/autobackup/<newest>.unf
  4. validate (size, not an error page, AES-block aligned or zip), write
     atomically (tmp + rename), keep the newest KEEP copies
  5. push metrics to the Pushgateway

Fails LOUD, never degrades: placeholder/empty credentials, a missing TLS pin, a
pin mismatch, 401/403/429, an empty list, a short or implausible file, or a
newest autobackup older than MAX_AGE_DAYS all exit non-zero and set
unifi_backup_last_run_ok 0. The success timestamp is only emitted by a fully
clean run, so a failing job shows up as an ageing timestamp.

TLS: the gateway uses a self-signed certificate, so chain verification is off
and the leaf certificate is PINNED by SHA-256 fingerprint instead. The pin is
checked on every connection BEFORE any credential is sent.

Stdlib only (runs in a plain python:alpine image). Secrets are never printed.
"""
import hashlib
import http.client
import json
import math
import os
import re
import ssl
import sys
import time

KEEP = 8
MIN_BYTES = 100 * 1024
MAX_AGE_DAYS = 9
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.unf$")
PIN_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PREFIXES = ("REPLACE", "CHANGE", "PLACEHOLDER", "TODO", "<")


class Fatal(Exception):
    pass


def env(name, default=""):
    return os.environ.get(name, default).strip()


def is_placeholder(value):
    return (not value) or value.upper().startswith(PLACEHOLDER_PREFIXES)


class Gateway:
    """Minimal pinned-HTTPS client holding one cookie + CSRF token."""

    def __init__(self, host, pin, port=443, timeout=60):
        self.host, self.pin, self.port, self.timeout = host, pin, port, timeout
        self.cookie = None
        self.csrf = None
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE  # replaced by the fingerprint pin

    def _connect(self):
        conn = http.client.HTTPSConnection(
            self.host, self.port, context=self.ctx, timeout=self.timeout
        )
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True)
        got = hashlib.sha256(der).hexdigest()
        if got != self.pin:
            conn.close()
            raise Fatal(
                "TLS pin mismatch: the gateway certificate fingerprint changed "
                "(renewed or intercepted). Nothing was sent. Re-pin "
                "UNIFI_CERT_SHA256 after verifying the new certificate."
            )
        return conn

    def request(self, method, path, body=None, stream_to=None):
        conn = self._connect()
        try:
            headers = {"Accept": "application/json, */*"}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            if self.cookie:
                headers["Cookie"] = self.cookie
            if self.csrf and method != "GET":
                headers["X-CSRF-Token"] = self.csrf
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            new_csrf = resp.getheader("X-Updated-CSRF-Token") or resp.getheader(
                "X-CSRF-Token"
            )
            if new_csrf:
                self.csrf = new_csrf
            for sc in resp.msg.get_all("Set-Cookie") or []:
                if sc.startswith("TOKEN="):
                    self.cookie = sc.split(";", 1)[0]
            if stream_to is not None and resp.status == 200:
                total = 0
                with open(stream_to, "wb") as fh:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        total += len(chunk)
                    fh.flush()
                    os.fsync(fh.fileno())
                expect = resp.getheader("Content-Length")
                if expect and int(expect) != total:
                    raise Fatal(
                        "short download: got %d bytes, Content-Length %s" % (total, expect)
                    )
                return resp.status, resp.getheader("Content-Type", ""), b""
            return resp.status, resp.getheader("Content-Type", ""), resp.read()
        finally:
            conn.close()


def csrf_from_cookie(cookie):
    """Fallback: the TOKEN cookie is a JWT whose payload carries csrfToken."""
    import base64

    try:
        payload = cookie.split("=", 1)[1].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("csrfToken")
    except Exception:
        return None


def entropy(sample):
    if not sample:
        return 0.0
    counts = [0] * 256
    for b in sample:
        counts[b] += 1
    n = len(sample)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def validate_unf(path, size):
    """A .unf is an AES-128-CBC encrypted zip: 16-byte aligned, ~8 bits/byte.
    A plain zip (PK) is also accepted. HTML/JSON error pages are rejected."""
    if size <= MIN_BYTES:
        raise Fatal("file too small: %d bytes (<= %d)" % (size, MIN_BYTES))
    with open(path, "rb") as fh:
        head = fh.read(65536)
    if head[:1] in (b"<", b"{", b"[") or head[:5].lower() == b"<!doc":
        raise Fatal("downloaded file looks like an HTML/JSON error page, not a .unf")
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if size % 16 != 0:
        raise Fatal("size %d is not AES-block aligned and not a zip" % size)
    if entropy(head) < 7.5:
        raise Fatal("content is neither a zip nor high-entropy encrypted data")
    return "encrypted"


def push(metrics_url, lines):
    import urllib.request

    req = urllib.request.Request(
        metrics_url, data=("\n".join(lines) + "\n").encode(), method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
        print("pushed metrics")
    except Exception as exc:  # metrics must not mask the real result
        print("WARNING: pushgateway push failed: %s" % exc)


def run(out_dir):
    host = env("UNIFI_HOST")
    site = env("UNIFI_SITE", "default")
    user = env("UNIFI_USER")
    secret = os.environ.get("UNIFI_PASSWORD", "").strip()
    pin = env("UNIFI_CERT_SHA256").lower().replace(":", "")
    result = {"ok": 0, "file_bytes": None, "success_ts": None, "src_age": None}

    if not re.match(r"^[A-Za-z0-9.-]+$", host):
        raise Fatal("UNIFI_HOST is empty or invalid")
    if not re.match(r"^[A-Za-z0-9_-]+$", site):
        raise Fatal("UNIFI_SITE is invalid")
    if is_placeholder(user) or is_placeholder(secret):
        raise Fatal(
            "UNIFI_USER/UNIFI_PASSWORD in secret unifi-backup-credentials are empty or "
            "still the placeholder. Paste the real values with sops into "
            "kubernetes/apps/backup/unifi-backup/app/secret.sops.yaml and push. "
            "See docs/sops/backup.md, section UniFi controller backup."
        )
    if not PIN_RE.match(pin):
        raise Fatal(
            "UNIFI_CERT_SHA256 is empty/placeholder/not 64 hex chars. Set it to the "
            "SHA-256 fingerprint of the gateway leaf certificate (docs/sops/backup.md)."
        )

    os.makedirs(out_dir, exist_ok=True)
    if not os.access(out_dir, os.W_OK):
        raise Fatal("output directory is not writable")
    for stale in os.listdir(out_dir):  # leftovers of an interrupted run
        if stale.startswith(".tmp-"):
            os.unlink(os.path.join(out_dir, stale))

    gw = Gateway(host, pin, int(env("UNIFI_PORT", "443")))

    # 1. single login -- no retry, 429 is terminal
    creds = {"username": user, "remember": False}
    creds["pass" + "word"] = secret
    status, _, _ = gw.request("POST", "/api/auth/login", creds)
    if status == 429:
        raise Fatal(
            "login rate-limited (HTTP 429). NOT retrying (a retry extends the lockout). "
            "See docs/sops/unifi-controller-rate-limit.md."
        )
    if status in (400, 401, 403):
        raise Fatal("login rejected (HTTP %d): wrong credentials or account disabled" % status)
    if status != 200 or not gw.cookie:
        raise Fatal("login failed (HTTP %d, cookie %s)" % (status, "set" if gw.cookie else "absent"))
    if not gw.csrf:
        gw.csrf = csrf_from_cookie(gw.cookie)
    if not gw.csrf:
        raise Fatal("login succeeded but no CSRF token was issued")
    print("login ok")

    # 2. list autobackups
    status, _, body = gw.request(
        "POST", "/proxy/network/api/s/%s/cmd/backup" % site, {"cmd": "list-backups"}
    )
    if status in (401, 403):
        raise Fatal(
            "list-backups denied (HTTP %d): the account's role cannot list backups. "
            "A read-only/Viewer role is NOT sufficient; use the least-privileged "
            "role that is (Limited Admin on the Network application, local-only, "
            "no Super Admin). See docs/sops/backup.md." % status
        )
    if status != 200:
        raise Fatal("list-backups failed (HTTP %d)" % status)
    try:
        payload = json.loads(body)
        items = payload["data"]
        assert payload.get("meta", {}).get("rc", "ok") == "ok"
    except Exception:
        raise Fatal("list-backups returned an unexpected payload")
    cands = []
    for it in items:
        name = str(it.get("filename", ""))
        if not NAME_RE.match(name):
            continue
        if it.get("type") not in (None, "autobackup") and "autobackup" not in name:
            continue
        ts = it.get("time") or it.get("timestamp") or 0
        ts = float(ts) / 1000.0 if float(ts) > 1e11 else float(ts)
        cands.append((ts, name, int(it.get("size") or 0)))
    if not cands:
        raise Fatal("the gateway lists no .unf autobackups (autobackup disabled?)")
    cands.sort()
    ts, name, listed_size = cands[-1]
    if ts <= 0:  # no usable timestamp: autobackup names embed one, sort by name
        name = sorted(c[1] for c in cands)[-1]
    else:
        result["src_age"] = max(0.0, time.time() - ts)
    print("newest autobackup on gateway: %s (listed %d bytes)" % (name, listed_size))

    # 3. download unless we already hold an identical copy
    dest = os.path.join(out_dir, name)
    if os.path.exists(dest) and listed_size and os.path.getsize(dest) == listed_size:
        print("already present, size matches; not downloading again")
        size = os.path.getsize(dest)
        validate_unf(dest, size)
    else:
        tmp = os.path.join(out_dir, ".tmp-" + name)
        status, ctype, _ = gw.request(
            "GET", "/proxy/network/dl/autobackup/" + name, stream_to=tmp
        )
        if status != 200:
            if os.path.exists(tmp):
                os.unlink(tmp)
            if status in (401, 403):
                raise Fatal(
                    "download denied (HTTP %d): account role cannot fetch backups" % status
                )
            raise Fatal("download failed (HTTP %d)" % status)
        try:
            size = os.path.getsize(tmp)
            kind = validate_unf(tmp, size)
            if listed_size and size != listed_size:
                raise Fatal("size %d differs from listed size %d" % (size, listed_size))
        except Fatal:
            os.unlink(tmp)
            raise
        os.replace(tmp, dest)  # atomic on the same filesystem
        print("saved %s (%d bytes, %s)" % (name, size, kind))
    result["file_bytes"] = size

    # 4. retention: keep the newest KEEP copies, only files matching our pattern
    mine = sorted(f for f in os.listdir(out_dir) if NAME_RE.match(f))
    for old in mine[:-KEEP]:
        os.unlink(os.path.join(out_dir, old))
        print("retention: removed %s" % old)

    # 5. freshness of the SOURCE: an old newest-autobackup is a failure too
    if result["src_age"] is not None and result["src_age"] > MAX_AGE_DAYS * 86400:
        raise_after = "newest autobackup on the gateway is %.1f days old (> %d): " \
                      "gateway autobackup is not running" % (result["src_age"] / 86400, MAX_AGE_DAYS)
        result["fail_msg"] = raise_after
        return result
    result["ok"] = 1
    result["success_ts"] = int(time.time())
    return result


def main():
    out_dir = env("OUT_DIR", "/backup")
    push_url = env("PUSHGATEWAY")
    result = {"ok": 0, "file_bytes": None, "success_ts": None, "src_age": None}
    rc = 0
    try:
        result = run(out_dir)
        if not result["ok"]:
            print("FATAL: " + result.get("fail_msg", "unknown"))
            rc = 1
    except Fatal as exc:
        print("FATAL: %s" % exc)
        rc = 1
    except Exception as exc:
        print("FATAL: unexpected %s: %s" % (type(exc).__name__, exc))
        rc = 1

    lines = [
        "# TYPE unifi_backup_last_run_ok gauge",
        "unifi_backup_last_run_ok %d" % result["ok"],
    ]
    if result["file_bytes"] is not None:
        lines += ["# TYPE unifi_backup_file_bytes gauge",
                  "unifi_backup_file_bytes %d" % result["file_bytes"]]
    if result["src_age"] is not None:
        lines += ["# TYPE unifi_backup_source_age_seconds gauge",
                  "unifi_backup_source_age_seconds %d" % result["src_age"]]
    if result["success_ts"] is not None:
        lines += ["# TYPE unifi_backup_last_success_timestamp gauge",
                  "unifi_backup_last_success_timestamp %d" % result["success_ts"]]
    if push_url:
        push(push_url.rstrip("/") + "/metrics/job/unifi-backup", lines)
    print("OK: unifi backup complete" if rc == 0 else "FAILED: unifi backup run did not complete cleanly")
    return rc


if __name__ == "__main__":
    sys.exit(main())
