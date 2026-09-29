"""Tests for mail-ingest against a real in-process SMTP server (aiosmtpd).

Run: python -m pytest containers/mail-ingest/tests
"""

from __future__ import annotations

import asyncio
import socket
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from aiosmtpd.controller import Controller

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import main  # noqa: E402

KEY = "k" * 48
DOMAIN = "example.test"
RCPT = f"alice@{DOMAIN}"
SENDER = "bob@sender.test"
MSG = b"From: bob@sender.test\r\nTo: alice@example.test\r\nSubject: hi\r\n\r\nhello\r\n.leading dot\r\n"


class Handler:
    """Scriptable SMTP behaviour: set rcpt/data replies or a delay per test."""

    def __init__(self):
        self.rcpt_reply = None
        self.data_reply = "250 2.0.0 queued as TEST"
        self.delay = 0.0
        self.received = []

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if self.rcpt_reply:
            return self.rcpt_reply
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.data_reply.startswith("2"):
            self.received.append((envelope.mail_from, list(envelope.rcpt_tos), envelope.content))
        return self.data_reply


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def smtp():
    handler = Handler()
    ctrl = Controller(handler, hostname="127.0.0.1", port=_free_port())
    ctrl.start()
    yield handler, ctrl.port
    ctrl.stop()


def _cfg(port: int, timeout: float = 3.0) -> dict:
    return main.load_config({
        "INGEST_HMAC_KEY": KEY,
        "SECRET_DOMAIN": DOMAIN.upper(),  # case-insensitive
        "STALWART_SMTP_HOST": "127.0.0.1",
        "STALWART_SMTP_PORT": str(port),
        "SMTP_TIMEOUT": str(timeout),
        "INGEST_HOSTNAME": "mail-ingest-test",
    })


def _headers(body: bytes = MSG, env_from: str = SENDER, env_to: str = RCPT, ts: int | None = None,
             size: int | None = None, key: str = KEY, sig: str | None = None) -> dict:
    ts = int(time.time()) if ts is None else ts
    size = len(body) if size is None else size
    if sig is None:
        sig = main.signature(key.encode(), str(ts), env_from, env_to, str(size))
    return {
        "X-Env-From": quote(env_from, safe=""),
        "X-Env-To": quote(env_to, safe=""),
        "X-Ts": str(ts),
        "X-Raw-Size": str(size),
        "X-Sig": sig,
        "Content-Type": "message/rfc822",
    }


@pytest.fixture
async def client(aiohttp_client, smtp):
    handler, port = smtp
    c = await aiohttp_client(main.make_app(_cfg(port)))
    c.handler = handler
    return c


async def post(client, body=MSG, **kw):
    return await client.post("/v1/ingest", data=body, headers=_headers(body, **kw))


# ── happy path ────────────────────────────────────────────────────────────────

async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status == 200 and await r.text() == "ok"


async def test_delivered_200_envelope_and_received_header(client):
    r = await post(client)
    assert r.status == 200, await r.text()
    body = await r.json()
    assert body["status"] == "delivered" and body["reply"].startswith("250")
    [(mail_from, rcpts, content)] = client.handler.received
    assert mail_from == SENDER and rcpts == [RCPT]
    assert content.startswith(b"Received: from cloudflare-email-routing by mail-ingest-test")
    assert b"for <alice@example.test>" in content
    assert content.endswith(MSG.rstrip(b"\r\n")) or MSG.rstrip(b"\r\n") in content
    assert b"\r\n.leading dot" in content  # dot-stuffing round-trips


async def test_null_sender_bounce_delivered(client):
    r = await post(client, env_from="")
    assert r.status == 200, await r.text()
    assert client.handler.received[0][0] == "<>"


async def test_non_ascii_percent_encoded_envelope(client):
    r = await post(client, env_from="jörg@sender.test")
    # aiosmtpd without SMTPUTF8 refuses a UTF-8 MAIL FROM with a 5xx: must map to 422, not crash.
    assert r.status in (200, 422)


# ── SMTP outcome mapping ─────────────────────────────────────────────────────

async def test_rcpt_5xx_maps_422_with_reply_text(client):
    client.handler.rcpt_reply = "550 5.1.1 mailbox does not exist"
    r = await post(client)
    assert r.status == 422
    assert "550" in (await r.json())["reason"] and "mailbox does not exist" in (await r.json())["reason"]


async def test_rcpt_4xx_maps_503(client):
    client.handler.rcpt_reply = "451 4.3.0 try later"
    r = await post(client)
    assert r.status == 503
    assert "451" in (await r.json())["reason"]


async def test_data_5xx_maps_422(client):
    client.handler.data_reply = "554 5.7.1 spam detected"
    r = await post(client)
    assert r.status == 422
    assert "spam detected" in (await r.json())["reason"]


async def test_data_4xx_maps_503(client):
    client.handler.data_reply = "452 4.3.1 insufficient storage"
    r = await post(client)
    assert r.status == 503


async def test_connection_refused_maps_503(aiohttp_client):
    c = await aiohttp_client(main.make_app(_cfg(_free_port())))
    r = await post(c)
    assert r.status == 503
    assert (await r.json())["status"] == "deferred"


async def test_smtp_timeout_maps_503(aiohttp_client, smtp):
    handler, port = smtp
    handler.delay = 3
    c = await aiohttp_client(main.make_app(_cfg(port, timeout=0.5)))
    t0 = time.monotonic()
    r = await post(c)
    assert r.status == 503
    assert time.monotonic() - t0 < 3


# ── request validation ───────────────────────────────────────────────────────

async def test_missing_sig_401(client):
    h = _headers()
    del h["X-Sig"]
    r = await client.post("/v1/ingest", data=MSG, headers=h)
    assert r.status == 401


async def test_missing_envelope_header_401(client):
    h = _headers()
    del h["X-Env-To"]
    r = await client.post("/v1/ingest", data=MSG, headers=h)
    assert r.status == 401


async def test_bad_sig_401(client):
    r = await post(client, key="wrong-key-" * 5)
    assert r.status == 401
    assert client.handler.received == []


async def test_sig_binds_recipient(client):
    h = _headers()
    h["X-Env-To"] = quote(f"mallory@{DOMAIN}", safe="")
    r = await client.post("/v1/ingest", data=MSG, headers=h)
    assert r.status == 401


async def test_garbage_sig_401(client):
    r = await post(client, sig="zzé" * 10)
    assert r.status == 401


@pytest.mark.parametrize("delta", [-301, 301, -10_000])
async def test_ts_skew_401(client, delta):
    r = await post(client, ts=int(time.time()) + delta)
    assert r.status == 401


async def test_ts_within_skew_ok(client):
    r = await post(client, ts=int(time.time()) - 290)
    assert r.status == 200


async def test_body_shorter_than_declared_400(client):
    r = await post(client, size=len(MSG) + 5)
    assert r.status == 400
    assert client.handler.received == []


async def test_body_longer_than_declared_400(client):
    r = await post(client, size=len(MSG) - 5)
    assert r.status == 400


async def test_oversize_413(client):
    r = await client.post("/v1/ingest", data=b"x",
                          headers=_headers(b"x", size=main.MAX_SIZE + 1))
    assert r.status == 413


async def test_foreign_recipient_422(client):
    r = await post(client, env_to="alice@other.test")
    assert r.status == 422
    assert client.handler.received == []


async def test_subdomain_recipient_422(client):
    r = await post(client, env_to=f"alice@sub.{DOMAIN}")
    assert r.status == 422


async def test_multi_recipient_422(client):
    r = await post(client, env_to=f"a@{DOMAIN},b@{DOMAIN}")
    assert r.status == 422


def test_config_requires_key_and_domain():
    with pytest.raises(SystemExit):
        main.load_config({"SECRET_DOMAIN": DOMAIN})
    with pytest.raises(SystemExit):
        main.load_config({"INGEST_HMAC_KEY": KEY})


async def test_smtp_injection_in_envelope_422(client):
    r = await post(client, env_from="bob@sender.test>\r\nRCPT TO:<victim@elsewhere.test")
    assert r.status == 422
    assert client.handler.received == []
