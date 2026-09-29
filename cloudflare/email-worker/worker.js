// Cloudflare Email Worker: hands every inbound message to the in-cluster
// mail-ingest shim (-> Stalwart) and falls back to a verified forward address
// whenever the cluster cannot take it.
//
// Outcome table (the Worker ALWAYS waits for the shim's answer):
//   shim 200                        -> done (delivered to Stalwart)
//   shim 422                        -> message.setReject(<Stalwart's reason>)  (permanent bounce)
//   anything else / throw / timeout -> message.forward(env.FALLBACK)
//
// Email Routing has no "try again later": an uncaught exception here is a
// permanent bounce to the sender, so every path is wrapped.
//
// Bindings (all set by terraform/cloudflare/email_worker.tf, never in git):
//   SECRET_DOMAIN         plain text   zone apex; shim is https://mail-ingest.<SECRET_DOMAIN>
//   HMAC_KEY              secret text  shared with the shim's INGEST_HMAC_KEY
//   ACCESS_CLIENT_ID      secret text  Cloudflare Access service token id
//   ACCESS_CLIENT_SECRET  secret text  Cloudflare Access service token secret
//   FALLBACK              secret text  verified Email Routing destination address
//
// Request contract (see containers/mail-ingest/app/main.py):
//   X-Sig = hex HMAC-SHA256(HMAC_KEY, `${ts}\n${from}\n${to}\n${rawSize}`)
// over the raw (decoded) addresses; the addresses travel percent-encoded so a
// non-ASCII (SMTPUTF8) envelope cannot make fetch() throw on the header value.
// The body is NOT hashed (a 25 MiB SHA-256 would blow the free plan's ~10 ms
// CPU budget); it is bound by its exact length instead.

const TIMEOUT_MS = 25_000;
const REASON_MAX = 200;

const enc = new TextEncoder();

async function sign(key, ts, from, to, size) {
  const k = await crypto.subtle.importKey(
    "raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", k, enc.encode(`${ts}\n${from}\n${to}\n${size}`));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Stream message.raw to the shim WITH a Content-Length. The Workers runtime
// provides FixedLengthStream for exactly this: a plain ReadableStream body would
// go out chunked, while FixedLengthStream sets Content-Length and errors the
// request if the byte count does not match (-> caught -> fallback forward).
// No `duplex: "half"` is needed in workerd (that is a Node/undici requirement);
// it is passed anyway because the runtime ignores unknown RequestInit members
// and it keeps the module runnable under Node for the unit tests.
function lengthBoundBody(raw, size) {
  if (typeof FixedLengthStream === "function") {
    const fls = new FixedLengthStream(size);
    raw.pipeTo(fls.writable).catch(() => {}); // failure surfaces on the fetch
    return fls.readable;
  }
  return raw;
}

function reasonFrom(text) {
  let reason = text;
  try {
    const j = JSON.parse(text);
    if (j && typeof j.reason === "string") reason = j.reason;
  } catch (_) { /* plain-text body */ }
  reason = String(reason || "550 5.1.1 rejected").replace(/[\r\n]+/g, " ").trim();
  return reason.length > REASON_MAX ? reason.slice(0, REASON_MAX) : reason;
}

async function fallback(message, env, why) {
  console.log(JSON.stringify({ event: "fallback", why }));
  try {
    const h = new Headers({ "X-Mail-Ingest-Fallback": String(why).replace(/[^\x20-\x7e]/g, "?").slice(0, 100) });
    await message.forward(env.FALLBACK, h);
  } catch (e) {
    // Nothing left to try. A reject at least gives the sender a readable bounce.
    console.log(JSON.stringify({ event: "fallback_failed", error: String(e && e.message || e) }));
    try { message.setReject("451 4.3.0 temporary delivery failure, please retry later"); } catch (_) {}
  }
}

async function handle(message, env, fetchImpl = fetch) {
  let why;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const ts = Math.floor(Date.now() / 1000).toString();
    const from = message.from || "";
    const to = message.to || "";
    const size = message.rawSize;
    const sig = await sign(env.HMAC_KEY, ts, from, to, String(size));
    const res = await fetchImpl(`https://mail-ingest.${env.SECRET_DOMAIN}/v1/ingest`, {
      method: "POST",
      body: lengthBoundBody(message.raw, size),
      duplex: "half",
      signal: ctl.signal,
      headers: {
        "CF-Access-Client-Id": env.ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.ACCESS_CLIENT_SECRET,
        "X-Env-From": encodeURIComponent(from),
        "X-Env-To": encodeURIComponent(to),
        "X-Ts": ts,
        "X-Raw-Size": String(size),
        "X-Sig": sig,
        "content-type": "message/rfc822",
      },
    });
    const text = await res.text().catch(() => "");
    if (res.status === 200) {
      console.log(JSON.stringify({ event: "delivered", size }));
      return "delivered";
    }
    if (res.status === 422) {
      const reason = reasonFrom(text);
      console.log(JSON.stringify({ event: "rejected", reason }));
      message.setReject(reason);
      return "rejected";
    }
    why = `shim status ${res.status}`;
  } catch (e) {
    why = e && e.name === "AbortError" ? "timeout" : `error: ${String(e && e.message || e)}`;
  } finally {
    clearTimeout(timer);
  }
  await fallback(message, env, why);
  return "forwarded";
}

// The default export is the ONLY export: workerd treats every named export as
// a potential entrypoint, so the test hooks ride on `_test` (an unknown member
// of the handler object, which the runtime ignores).
export default {
  _test: { handle, sign, TIMEOUT_MS },

  async email(message, env, _ctx) {
    try {
      await handle(message, env);
    } catch (e) {
      // handle() already catches everything; this is the last line of defence.
      try { await fallback(message, env, `outer: ${String(e && e.message || e)}`); } catch (_) {}
    }
  },
};
