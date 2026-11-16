# SOP: Mealie on the Samsung Family Hub (Chrome 108 compatibility)

> Description: How Mealie stays usable on the fridge's old browser via a gateway polyfill, and the check to run before every Mealie bump.
> Version: `2026.11.16`
> Last Updated: `2026-11-16`
> Owner: `homelab operator`

---

## 1) Description

The Samsung Family Hub fridge runs Chrome 108 (Tizen 7.0/7.2). Mealie v3.30.0 (Vuetify 4.3.0)
calls `Object.entries(...).toSorted(...)` unguarded; `toSorted` needs Chrome 110, so every page
was blank. Upstream declined to fix it (mealie-recipes/mealie#9178: update the browser or fork).
We chose a small gateway polyfill over a fork: no custom image, no per-release patching.

- Scope: namespace `office`, app `mealie`; Envoy Gateway.
- Prerequisites: the fridge, Chrome, `runbooks/mealie-chrome108-scan.py`.
- Out of scope: other Tizen browsers/apps.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Polyfill | `kubernetes/apps/office/mealie/app/envoyextensionpolicy.yaml` (`mealie-array-polyfill`) |
| Mechanism | Envoy Lua injects a `<script data-cb-polyfill>` first in `<head>` of `text/html` responses on the mealie HTTPRoute only |
| Polyfilled | `Array.prototype.toSorted`, `toReversed`, `toSpliced`, `with` |
| Requires | `extensionApis.enableLua: true` in `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml` |
| Update gate | `*mealie*` deny rule in `runbooks/auto-update-policy.yaml` (plan lane only) |
| Pre-bump scan | `runbooks/mealie-chrome108-scan.py` + `runbooks/mealie-chrome108-baseline.json` |
| Upstream | https://github.com/mealie-recipes/mealie/issues/9178 (declined) |

---

## 3) Blueprints

N/A. Plain Kubernetes manifests (EnvoyExtensionPolicy), no Authentik blueprint.

---

## 4) Operational Instructions

Before ANY Mealie version bump (chart, image tag or Renovate PR):

1. Run the scan against a running instance of the target version (a throwaway test route with
   emptyDir storage worked; `git log --stat` for the removed `mealie-test` app has a template):
   `python3 runbooks/mealie-chrome108-scan.py https://<test-host>`
2. Exit 0: bump as normal. Exit 1: a new post-Chrome-108 API appears. Read the hit (many are
   feature-detected and harmless), then either extend the polyfill, add the reviewed feature to
   `mealie-chrome108-baseline.json`, or decide to fork. Exit 2: the scan was blind; never a pass.
3. After the bump, open the production URL on the fridge (private tab) and confirm recipes load.

Decision recorded 2026-11-16: keep the polyfill as long as it holds. Fork Mealie only if a
future release needs something we cannot polyfill.

---

## 5) Examples

```bash
python3 runbooks/mealie-chrome108-scan.py https://mealie.example
curl -s -L -H 'Accept: text/html' https://mealie.example/login | grep -c data-cb-polyfill   # expect 1
```

---

## 6) Verification Tests

- Page contains the marker (command above prints 1).
- `kubectl -n office get envoyextensionpolicy mealie-array-polyfill` shows Accepted.
- Fridge: login page and recipe list render.

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Fridge blank again after a bump | New API not polyfilled | Console on desktop Chrome with a Chrome 108 UA/emulation; extend the polyfill |
| Marker count 0 | Policy missing, Lua disabled, or upstream response gzip | Check `enableLua`, policy status; the Lua strips `accept-encoding` on HTML requests |
| Page works on desktop, blank on fridge only after cache | Old service worker precache | Private tab or clear site data on the fridge |

---

## 8) Diagnose Examples

```bash
kubectl -n office describe envoyextensionpolicy mealie-array-polyfill
kubectl -n network logs deploy/envoy-gateway --tail=50 | grep -i lua
```

---

## 9) Health Check

Run the pre-bump scan quarterly even without a bump; it also confirms the marker is served.

---

## 10) Security Check

The injected script is static and contains no user data. The policy touches only the mealie HTTPRoute. Mealie sets no CSP, so inline script is allowed; if a CSP is ever added the polyfill must move to a nonce or hash.

---

## 11) Rollback Plan

Revert the commit that added `envoyextensionpolicy.yaml` (`3ed54cf0a`). The fridge goes blank again, nothing else changes. Gateway-wide `enableLua` can stay.

---

## 12) References

- `docs/sops/gateway-api-httproute.md`
- https://github.com/mealie-recipes/mealie/issues/9178

## Version History

- 2026.11.16: initial version.
