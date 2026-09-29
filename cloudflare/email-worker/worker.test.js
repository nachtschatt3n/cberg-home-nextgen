// node --test  (Node >= 20; no dependencies)
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker from "./worker.js";

const { handle, sign } = worker._test;

const ENV = {
  SECRET_DOMAIN: "example.test",
  HMAC_KEY: "k".repeat(48),
  ACCESS_CLIENT_ID: "id.access",
  ACCESS_CLIENT_SECRET: "secret",
  FALLBACK: "fallback@elsewhere.test",
};
const RAW = "Subject: hi\r\n\r\nbody\r\n";

function mkMessage({ from = "bob@sender.test", to = "alice@example.test", forwardThrows = false } = {}) {
  const bytes = new TextEncoder().encode(RAW);
  return {
    from, to, rawSize: bytes.length,
    raw: new ReadableStream({ start(c) { c.enqueue(bytes); c.close(); } }),
    rejected: null, forwarded: null,
    setReject(r) { this.rejected = r; },
    async forward(addr, headers) {
      if (forwardThrows) throw new Error("not verified");
      this.forwarded = { addr, headers };
    },
  };
}

function mkFetch(status, body = "", capture = {}) {
  return async (url, init) => {
    capture.url = url; capture.init = init;
    capture.body = await new Response(init.body).text();
    return new Response(body, { status });
  };
}

test("signature matches the shim's HMAC definition", async () => {
  const got = await sign("key", "1700000000", "a@b", "c@d", "42");
  const want = createHmac("sha256", "key").update("1700000000\na@b\nc@d\n42").digest("hex");
  assert.equal(got, want);
});

test("200 -> delivered, correct request shape", async () => {
  const m = mkMessage(); const cap = {};
  assert.equal(await handle(m, ENV, mkFetch(200, '{"status":"delivered"}', cap)), "delivered");
  assert.equal(cap.url, "https://mail-ingest.example.test/v1/ingest");
  assert.equal(cap.init.method, "POST");
  const h = cap.init.headers;
  assert.equal(h["CF-Access-Client-Id"], "id.access");
  assert.equal(h["CF-Access-Client-Secret"], "secret");
  assert.equal(h["X-Raw-Size"], String(m.rawSize));
  assert.equal(h["content-type"], "message/rfc822");
  const want = createHmac("sha256", ENV.HMAC_KEY)
    .update(`${h["X-Ts"]}\nbob@sender.test\nalice@example.test\n${m.rawSize}`).digest("hex");
  assert.equal(h["X-Sig"], want);
  assert.ok(Math.abs(Number(h["X-Ts"]) - Date.now() / 1000) < 5);
  assert.equal(cap.body, RAW);
  assert.equal(m.rejected, null); assert.equal(m.forwarded, null);
});

test("non-ASCII envelope is percent-encoded, signature over decoded value", async () => {
  const m = mkMessage({ from: "jörg@sender.test" }); const cap = {};
  await handle(m, ENV, mkFetch(200, "", cap));
  assert.equal(cap.init.headers["X-Env-From"], "j%C3%B6rg%40sender.test");
  const h = cap.init.headers;
  const want = createHmac("sha256", ENV.HMAC_KEY)
    .update(`${h["X-Ts"]}\njörg@sender.test\nalice@example.test\n${m.rawSize}`).digest("hex");
  assert.equal(h["X-Sig"], want);
});

test("422 -> setReject with the shim's reason, truncated and single-line", async () => {
  const m = mkMessage();
  const reason = "550 5.1.1 no such user\r\n" + "x".repeat(500);
  assert.equal(await handle(m, ENV, mkFetch(422, JSON.stringify({ status: "rejected", reason }))), "rejected");
  assert.ok(m.rejected.startsWith("550 5.1.1 no such user x"));
  assert.ok(!/[\r\n]/.test(m.rejected));
  assert.equal(m.rejected.length, 200);
  assert.equal(m.forwarded, null);
});

test("422 with plain-text body still rejects", async () => {
  const m = mkMessage();
  await handle(m, ENV, mkFetch(422, "554 spam"));
  assert.equal(m.rejected, "554 spam");
});

for (const status of [503, 500, 401, 403, 400, 413, 302]) {
  test(`${status} -> forward to FALLBACK`, async () => {
    const m = mkMessage();
    assert.equal(await handle(m, ENV, mkFetch(status, "nope")), "forwarded");
    assert.equal(m.forwarded.addr, ENV.FALLBACK);
    assert.equal(m.rejected, null);
  });
}

test("fetch throws -> forward", async () => {
  const m = mkMessage();
  assert.equal(await handle(m, ENV, async () => { throw new TypeError("network down"); }), "forwarded");
  assert.equal(m.forwarded.addr, ENV.FALLBACK);
});

test("timeout (abort) -> forward", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const m = mkMessage();
  const hanging = (_url, init) => new Promise((_, reject) => {
    init.signal.addEventListener("abort", () => {
      const e = new Error("aborted"); e.name = "AbortError"; reject(e);
    });
  });
  const p = handle(m, ENV, hanging);
  await new Promise((r) => setImmediate(r)); // let sign() + fetch() start
  await new Promise((r) => setImmediate(r));
  t.mock.timers.tick(25_000);
  assert.equal(await p, "forwarded");
  assert.equal(m.forwarded.headers.get("X-Mail-Ingest-Fallback"), "timeout");
});

test("forward itself throws -> setReject, nothing escapes", async () => {
  const m = mkMessage({ forwardThrows: true });
  assert.equal(await handle(m, ENV, mkFetch(503)), "forwarded");
  assert.match(m.rejected, /^451/);
});

test("default export never throws, even with broken env", async () => {
  const m = mkMessage();
  const origFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("boom"); };
  try {
    await worker.email(m, { ...ENV, HMAC_KEY: undefined }, {});
  } finally {
    globalThis.fetch = origFetch;
  }
  assert.equal(m.forwarded.addr, ENV.FALLBACK);
});
