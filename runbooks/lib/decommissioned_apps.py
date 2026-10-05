"""Which app directories under kubernetes/apps/ are DECOMMISSIONED (not deployed).

The house decommission idiom (ac7bf0e0, 2026-10-04) is to COMMENT OUT the app's
Flux Kustomization entry in its parent namespace kustomization and leave the
directory in git:

    resources:
     - ./affine/ks.yaml
     # - ./actual-budget/ks.yaml  # DISABLED 2026-10-04 (...)

Flux prunes the app, but every audit that discovers workloads by rglob-ing
kubernetes/apps/ kept reporting version findings for it — a planner was
dispatched for a version bump of an app that no longer runs.

The rule here is deliberately NARROW, because narrowing a detector to kill a
false positive has repeatedly created false negatives in this repo:

  A directory D is disabled ONLY when
    (a) some kustomization.yaml under kubernetes/apps/ carries a COMMENTED-OUT
        reference resolving to D (`# - ./D/ks.yaml`, `# - ./D`), AND
    (b) NO live reference anywhere under kubernetes/ resolves to D or into it —
        neither an uncommented kustomization `resources:`/`components:` entry
        nor a Flux Kustomization `spec.path` — from a file outside D itself.

Mere ABSENCE of a reference never disables anything: an app wired some other
way (a nested kustomization, another ks.yaml's spec.path, a future layout) stays
in scope. A kustomization.yaml that cannot be parsed contributes its live refs
by regex fallback, so a parse error can only keep a directory ENABLED.

The namespace level is handled by the same rule: if kubernetes/apps/
kustomization.yaml ever exists and comments out `./<ns>`, the whole namespace
directory is disabled (and everything under it, via `is_disabled()`).

Callers MUST report what they skipped (`skip_line()`), never skip silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_KS_FILENAMES = ("ks.yaml", "ks.yml", "kustomization.yaml", "kustomization.yml")

# `#` (one or more), optional space, `- `, optional quote, a relative path.
_COMMENTED_REF = re.compile(r"""^\s*#+\s*-\s+["']?(\.{0,2}/?[\w./-]+?)["']?\s*(?:#.*)?$""")
# Uncommented list item — used only as a fallback when YAML parsing fails.
_LIVE_REF = re.compile(r"""^\s*-\s+["']?(\.{0,2}/?[\w./-]+?)["']?\s*(?:#.*)?$""")
_FLUX_KS_PATH = re.compile(r"""^\s+path:\s*["']?(\.?/?kubernetes/[\w./-]+?)["']?\s*$""", re.M)


@dataclass(frozen=True)
class DisabledDir:
    path: Path          # absolute directory path
    rel: str            # repo-relative, for reporting
    referenced_from: str  # repo-relative kustomization.yaml carrying the comment
    line: int           # 1-based line number of the commented reference


def _ref_target(base_dir: Path, ref: str) -> Path | None:
    """Directory a kustomization reference points at, or None if not a path."""
    if "://" in ref or not ref or ref.startswith("#"):
        return None
    p = (base_dir / ref)
    try:
        p = p.resolve()
    except OSError:
        return None
    if p.name in _KS_FILENAMES or p.suffix in (".yaml", ".yml"):
        p = p.parent
    return p


def _within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _live_refs_of_kustomization(kfile: Path, text: str) -> list[Path]:
    base = kfile.parent
    refs: list[str] = []
    try:
        doc = yaml.safe_load(text)
        if isinstance(doc, dict):
            for key in ("resources", "components", "bases"):
                for r in doc.get(key) or []:
                    if isinstance(r, str):
                        refs.append(r)
        else:
            raise ValueError("not a mapping")
    except Exception:  # noqa: BLE001 — fail toward ENABLED: regex every live list item
        for ln in text.splitlines():
            m = _LIVE_REF.match(ln)
            if m and not ln.lstrip().startswith("#"):
                refs.append(m.group(1))
    out = []
    for r in refs:
        t = _ref_target(base, r)
        if t is not None:
            out.append(t)
    return out


def find_disabled_app_dirs(repo_root: str | Path) -> list[DisabledDir]:
    """All directories under kubernetes/apps/ that are commented-out-only."""
    root = Path(repo_root).resolve()
    kube = root / "kubernetes"
    apps = kube / "apps"
    if not apps.is_dir():
        return []

    candidates: dict[Path, tuple[str, int]] = {}
    # (source file, target dir) for every LIVE reference in the repo.
    live: list[tuple[Path, Path]] = []

    for kfile in sorted(kube.rglob("kustomization.y*ml")):
        try:
            text = kfile.read_text(errors="replace")
        except OSError:
            continue
        for t in _live_refs_of_kustomization(kfile, text):
            live.append((kfile, t))
        if not _within(kfile, apps):
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            m = _COMMENTED_REF.match(ln)
            if not m:
                continue
            ref = m.group(1)
            # Only a commented Flux-Kustomization file (ks.yaml) or a
            # commented DIRECTORY reference can disable a directory. A
            # commented plain manifest (`#- ./deployment.yaml` inside an
            # app/ kustomization) disables that one file, not its directory.
            leaf = ref.rstrip("/").rsplit("/", 1)[-1]
            if leaf.endswith((".yaml", ".yml")) and leaf not in _KS_FILENAMES:
                continue
            t = _ref_target(kfile.parent, ref)
            if t is None or not _within(t, apps) or t == apps or not t.is_dir():
                continue
            candidates.setdefault(t, (str(kfile.relative_to(root)), i))

    if not candidates:
        return []

    # Flux Kustomization spec.path is the other way to wire a directory in.
    for f in sorted(kube.rglob("*.y*ml")):
        if f.name.endswith((".sops.yaml", ".sops.yml")):
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if "kustomize.toolkit.fluxcd.io" not in text:
            continue
        for m in _FLUX_KS_PATH.finditer(text):
            live.append((f, (root / m.group(1)).resolve()))

    out: list[DisabledDir] = []
    for cand, (src, line) in sorted(candidates.items()):
        alive = any(
            _within(target, cand) and not _within(source, cand)
            for source, target in live
        )
        if not alive:
            out.append(DisabledDir(cand, str(cand.relative_to(root)), src, line))
    return out


def is_disabled(path: str | Path, disabled: list[DisabledDir]) -> bool:
    """True when `path` lies inside (or is) a disabled directory."""
    p = Path(path).resolve()
    return any(_within(p, d.path) for d in disabled)


def skip_line(disabled: list[DisabledDir]) -> str:
    """The visible report line every caller prints. Never skip silently."""
    if not disabled:
        return "skipped 0 decommissioned app dirs (no commented-out-only ks.yaml references)"
    names = ", ".join(d.rel.removeprefix("kubernetes/apps/") for d in disabled)
    return (f"skipped {len(disabled)} decommissioned app dir(s) "
            f"(ks.yaml reference commented out, no live reference): {names}")
