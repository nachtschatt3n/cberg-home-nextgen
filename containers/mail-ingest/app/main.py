"""mail-ingest -- HTTPS -> SMTP shim between the Cloudflare Email Worker and Stalwart.

Cloudflare Email Routing hands each inbound message (one envelope recipient per
invocation) to an Email Worker. The Worker POSTs the raw RFC 822 bytes here, with
the envelope in headers; this service re-injects it into Stalwart over plain SMTP
on the in-cluster port 25 and maps the SMTP outcome onto an HTTP status the
Worker can act on:

    SMTP 2xx                       -> 200  (delivered)
    SMTP 5xx                       -> 422  (Worker: message.setReject(reason))
    SMTP 4xx / connect / timeout   -> 503  (Worker: forward to the fallback mailbox)

Request contract (POST /v1/ingest):
    X-Env-From  envelope sender, percent-encoded (may be empty for bounces)
    X-Env-To    envelope recipient (exactly one), percent-encoded
    X-Ts        unix seconds when the Worker signed the request
    X-Raw-Size  exact byte length of the body
    X-Sig       hex HMAC-SHA256(INGEST_HMAC_KEY, f"{ts}\\n{from}\\n{to}\\n{size}")
                computed over the DECODED addresses

The HMAC deliberately does not cover the body: hashing up to 25 MiB would blow
the Worker's CPU budget. The body is bound by its exact size instead, and the
edge path is separately gated by a Cloudflare Access service token.

Logs are JSON, one object per line. They carry only the DOMAIN part of each
address and never any message content.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import socket
import sys
import time
import uuid
from email.utils import formatdate
from urllib.parse import unquote

import aiosmtplib
from aiohttp import web

MAX_SIZE = 30 * 1024 * 1024  # 30 MiB; Cloudflare caps at 25 MiB, Stalwart at 30 MiB
MAX_SKEW = 300  # seconds
CHUNK = 64 * 1024

log = logging.getLogger("mail-ingest")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            out.update(extra)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, separators=(",", ":"))


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())


def _domain(addr: str) -> str:
    """Domain part only -- full addresses never reach the logs."""
    if not addr:
        return "<>"
    return addr.rsplit("@", 1)[1].lower() if "@" in addr else "<none>"


def _event(level: int, msg: str, **fields) -> None:
    log.log(level, msg, extra={"fields": fields})


def signature(key: bytes, ts: str, env_from: str, env_to: str, size: str) -> str:
    payload = f"{ts}\n{env_from}\n{env_to}\n{size}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _json(http_status: int, **body) -> web.Response:
    return web.json_response(body, status=http_status)


def _received_header(env_to: str, req_id: str, hostname: str) -> bytes:
    # One logical header, folded; aiosmtplib normalises line endings to CRLF.
    return (
        f"Received: from cloudflare-email-routing by {hostname} (mail-ingest)\r\n"
        f"\twith HTTPS id {req_id}\r\n"
        f"\tfor <{env_to}>; {formatdate(localtime=False, usegmt=True)}\r\n"
    ).encode("utf-8")


async def ingest(request: web.Request) -> web.Response:
    cfg = request.app["cfg"]
    req_id = uuid.uuid4().hex[:16]
    started = time.monotonic()
    h = request.headers

    raw_from = h.get("X-Env-From")
    raw_to = h.get("X-Env-To")
    ts = h.get("X-Ts", "")
    size_s = h.get("X-Raw-Size", "")
    sig = h.get("X-Sig", "")

    # 1. Authenticate first: nothing below is evaluated for an unsigned caller.
    if raw_from is None or raw_to is None or not ts or not size_s or not sig:
        _event(logging.WARNING, "reject", req_id=req_id, status=401, reason="missing header")
        return _json(401, status="unauthorized", reason="missing signature header")
    try:
        env_from = unquote(raw_from, errors="strict")
        env_to = unquote(raw_to, errors="strict")
    except UnicodeDecodeError:
        _event(logging.WARNING, "reject", req_id=req_id, status=400, reason="bad encoding")
        return _json(400, status="bad_request", reason="envelope not valid percent-encoded UTF-8")
    expected = signature(cfg["key"], ts, env_from, env_to, size_s)
    if not hmac.compare_digest(expected.encode("ascii"), sig.strip().lower().encode("ascii", "replace")):
        _event(logging.WARNING, "reject", req_id=req_id, status=401, reason="bad signature")
        return _json(401, status="unauthorized", reason="bad signature")
    try:
        ts_i = int(ts)
        size = int(size_s)
    except ValueError:
        _event(logging.WARNING, "reject", req_id=req_id, status=400, reason="non-integer ts/size")
        return _json(400, status="bad_request", reason="X-Ts and X-Raw-Size must be integers")
    if abs(time.time() - ts_i) > MAX_SKEW:
        _event(logging.WARNING, "reject", req_id=req_id, status=401, reason="timestamp skew")
        return _json(401, status="unauthorized", reason="timestamp outside allowed skew")

    if any(ord(c) < 0x21 or c in "<>" for c in env_from + env_to):
        _event(logging.WARNING, "reject", req_id=req_id, status=422, reason="envelope syntax")
        return _json(422, status="rejected", reason="553 5.1.7 invalid envelope address")

    fields = dict(req_id=req_id, from_domain=_domain(env_from), to_domain=_domain(env_to), size=size)

    # 2. Cheap envelope checks before reading the body.
    if size < 0:
        _event(logging.WARNING, "reject", status=400, reason="negative size", **fields)
        return _json(400, status="bad_request", reason="negative size")
    if size > MAX_SIZE:
        _event(logging.WARNING, "reject", status=413, reason="too large", **fields)
        return _json(413, status="too_large", reason=f"message exceeds {MAX_SIZE} bytes")
    if "," in env_to or "@" not in env_to or _domain(env_to) != cfg["domain"]:
        _event(logging.WARNING, "reject", status=422, reason="recipient not local", **fields)
        return _json(422, status="rejected", reason="550 5.7.1 recipient domain not handled here")

    # 3. Read exactly `size` bytes; anything else is a truncated/extended body.
    body = bytearray()
    try:
        while True:
            chunk = await request.content.read(CHUNK)
            if not chunk:
                break
            body += chunk
            if len(body) > size:
                break
    except (asyncio.TimeoutError, ConnectionError) as exc:  # client went away
        _event(logging.WARNING, "reject", status=400, reason=f"body read failed: {type(exc).__name__}", **fields)
        return _json(400, status="bad_request", reason="body read failed")
    if len(body) != size:
        _event(logging.WARNING, "reject", status=400, reason="size mismatch", got=len(body), **fields)
        return _json(400, status="bad_request", reason="body length does not match X-Raw-Size")

    # 4. Deliver.
    message = _received_header(env_to, req_id, cfg["hostname"]) + bytes(body)
    status, reply, code = await deliver(cfg, env_from, env_to, message)
    fields.update(status=status, smtp_code=code, duration_ms=int((time.monotonic() - started) * 1000))
    if status == 200:
        _event(logging.INFO, "delivered", **fields)
        return _json(200, status="delivered", reply=reply)
    if status == 422:
        _event(logging.INFO, "rejected by stalwart", **fields)
        return _json(422, status="rejected", reason=reply)
    _event(logging.WARNING, "deferred", **fields)
    return _json(503, status="deferred", reason=reply)


def _reply(code: int, message: str) -> str:
    return f"{code} {message}".strip()


def _classify(code: int, message: str) -> tuple[int, str, int]:
    if 200 <= code < 300:
        return 200, _reply(code, message), code
    if 500 <= code < 600:
        return 422, _reply(code, message), code
    return 503, _reply(code, message), code


async def _transaction(cfg: dict, env_from: str, env_to: str, message: bytes) -> tuple[int, str, int]:
    utf8 = not (env_from + env_to).isascii()
    encoding = "utf-8" if utf8 else "ascii"
    smtp = aiosmtplib.SMTP(
        hostname=cfg["smtp_host"],
        port=cfg["smtp_port"],
        local_hostname=cfg["hostname"],
        start_tls=cfg["starttls"],
        use_tls=False,
        validate_certs=cfg["starttls"],
        timeout=cfg["smtp_timeout"],
    )
    async with smtp:
        await smtp.ehlo()
        opts: list[str] = []
        if smtp.supports_extension("size"):
            opts.append(f"SIZE={len(message)}")
        if utf8:
            if not smtp.supports_extension("smtputf8"):
                return 422, "553 5.6.7 non-ASCII address and upstream lacks SMTPUTF8", 553
            opts.append("SMTPUTF8")
        if env_from:
            await smtp.mail(env_from, options=opts, encoding=encoding)  # validates against injection
        else:
            # Null reverse-path (bounces / DSNs); aiosmtplib's quote_address refuses "".
            resp = await smtp.execute_command(b"MAIL", b"FROM:<>", *[o.encode("ascii") for o in opts])
            if resp.code != 250:
                return _classify(resp.code, resp.message)
        await smtp.rcpt(env_to, encoding=encoding)
        resp = await smtp.data(message)
    return _classify(resp.code, resp.message)


async def deliver(cfg: dict, env_from: str, env_to: str, message: bytes) -> tuple[int, str, int]:
    """Return (http_status, smtp_reply_text, smtp_code). code 0 = no SMTP reply."""
    try:
        return await asyncio.wait_for(
            _transaction(cfg, env_from, env_to, message),
            timeout=cfg["smtp_timeout"] + 2,
        )
    except (aiosmtplib.SMTPConnectError, aiosmtplib.SMTPTimeoutError,
            aiosmtplib.SMTPServerDisconnected, asyncio.TimeoutError, OSError) as exc:
        # Checked before SMTPResponseException: a 4xx/5xx greeting is a
        # SMTPConnectResponseError (both), and an unreachable/greylisting
        # upstream must defer to the fallback, never bounce.
        return 503, f"451 4.4.1 upstream unavailable ({type(exc).__name__})", 0
    except aiosmtplib.SMTPResponseException as exc:
        # MAIL / RCPT / DATA / EHLO refused with a reply code.
        return _classify(exc.code, exc.message)
    except ValueError:
        # aiosmtplib refused an address that could inject SMTP syntax.
        return 422, "553 5.1.7 invalid envelope address", 553
    except aiosmtplib.SMTPException as exc:
        return 503, f"451 4.3.0 smtp error ({type(exc).__name__})", 0


async def healthz(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


def load_config(env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    key = env.get("INGEST_HMAC_KEY", "")
    domain = env.get("SECRET_DOMAIN", "").strip().lower()
    if len(key) < 32:
        raise SystemExit("INGEST_HMAC_KEY must be set (>= 32 chars)")
    if not domain:
        raise SystemExit("SECRET_DOMAIN must be set")
    return {
        "key": key.encode("utf-8"),
        "domain": domain,
        "smtp_host": env.get("STALWART_SMTP_HOST", "stalwart"),
        "smtp_port": int(env.get("STALWART_SMTP_PORT", "25")),
        "smtp_timeout": float(env.get("SMTP_TIMEOUT", "20")),
        # In-cluster hop: Stalwart's cert names mail.<domain>, not the Service,
        # so STARTTLS would fail verification. Off unless explicitly enabled.
        "starttls": env.get("SMTP_STARTTLS", "false").lower() in ("1", "true", "yes"),
        "hostname": env.get("INGEST_HOSTNAME") or socket.gethostname(),
    }


def make_app(cfg: dict) -> web.Application:
    # client_max_size only guards request.read(); ingest streams request.content
    # itself, capped by X-Raw-Size, so this is a second belt.
    app = web.Application(client_max_size=MAX_SIZE + 1024)
    app["cfg"] = cfg
    app.router.add_post("/v1/ingest", ingest)
    app.router.add_get("/healthz", healthz)
    return app


def main() -> None:
    _setup_logging()
    cfg = load_config()
    _event(logging.INFO, "starting", smtp_host=cfg["smtp_host"], smtp_port=cfg["smtp_port"], domain=cfg["domain"])
    web.run_app(
        make_app(cfg),
        host=os.environ.get("LISTEN_HOST", "0.0.0.0"),
        port=int(os.environ.get("LISTEN_PORT", "8080")),
        access_log=None,
        print=None,
    )


if __name__ == "__main__":
    main()
