#!/usr/bin/env python3
"""Regression tests: the private-image credential-gap veto is gated on prior
findings, not on credential presence.

Incident (2026-08-24): `security-check.py` treated "no registry credentials
this run" as proof the run was a deliberately credential-less standalone
invocation — a STEADY STATE, safe to report without arming the auto-close
veto (docs/sops/sweep-findings-lifecycle.md §4.3's own worked example argued
this explicitly). But "no creds this run" cannot distinguish that from an
ORCHESTRATED sweep whose `gh auth token` fetch failed mid-schedule — a
TRANSIENT blip that §4.3's own rule says must veto. An expired token silently
auto-closed 44 findings across ~9 private images in one cycle.

The fix replaces the credential-presence discriminator with a behavioural one:
does a prior OPEN finding already exist for this image? An image with none has
nothing to protect regardless of why it's unscannable; an image with one is
exactly the row auto-close would wrongly resolve. `_private_images_at_risk()`
is the pure predicate under test — split out specifically so this suite does
not need a database.

Run: python3 runbooks/tests/test-security-credgap-veto.py
"""
import importlib.util
import os
import pathlib
import sys

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


print("security credential-gap veto tests\n")

IMG_A = "ghcr.io/nachtschatt3n/paperclip:v2.3.0"
IMG_B = "ghcr.io/nachtschatt3n/ai-sre:v1.0.0"
IMG_C = "ghcr.io/nachtschatt3n/hermes-agent:v0.5.0"

# --- direction 1: the incident itself -- expired-token blip must still veto -
prior_with_finding = [
    ("`ghcr.io/nachtschatt3n/paperclip:v2.3.0`: 2 fixable CRITICAL CVE(s)", None),
]
check("image WITH a prior open finding is flagged at-risk (must veto)",
      sc._private_images_at_risk([IMG_A], prior_with_finding), [IMG_A])

# --- direction 2: no prior finding -> nothing to protect, no veto ----------
check("image with NO prior finding is not flagged (nothing to protect)",
      sc._private_images_at_risk([IMG_B], prior_with_finding), [])

# --- direction 3: mixed batch -- only the ones with prior findings ----------
prior_mixed = [
    ("`ghcr.io/nachtschatt3n/paperclip:v2.3.0`: 1 fixable CRITICAL CVE(s)", None),
    ("`ghcr.io/nachtschatt3n/hermes-agent:v0.5.0`: 3 fixable HIGH CVE(s)", None),
]
check("mixed batch: only images with a prior finding are flagged",
      sorted(sc._private_images_at_risk([IMG_A, IMG_B, IMG_C], prior_mixed)),
      sorted([IMG_A, IMG_C]))

# --- direction 4: matches via structured metadata too, not just title ------
prior_via_metadata = [
    ("some other title entirely", {"image": "ghcr.io/nachtschatt3n/ai-sre"}),
]
check("prior finding matched via metadata.image (not just title substring)",
      sc._private_images_at_risk([IMG_B], prior_via_metadata), [IMG_B])

# --- direction 5: empty prior-findings list (fresh DB / query failure) -----
check("no prior findings at all -> nothing flagged (fail-safe, not fail-open)",
      sc._private_images_at_risk([IMG_A, IMG_B], []), [])

# --- direction 6: _open_findings_titles degrades safely, never raises ------
check("_open_findings_titles(None, ...) returns [] without a DSN",
      sc._open_findings_titles(None, "security"), [])
check("_open_findings_titles with an unreachable DSN returns [] (never raises)",
      sc._open_findings_titles("postgresql://nope:5432/nope", "security"), [])

# --- direction 7: unrelated finding titles must not false-positive ---------
prior_unrelated = [
    ("Talos v1.13.8 -> v1.13.9 available", None),
    ("Longhorn volume esphome-config allocation is high", None),
]
check("unrelated findings do not falsely flag a private image at-risk",
      sc._private_images_at_risk([IMG_A, IMG_B, IMG_C], prior_unrelated), [])

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
