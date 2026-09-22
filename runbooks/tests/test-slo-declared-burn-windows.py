#!/usr/bin/env python3
"""Pin that slo-check.py evaluates the burn windows the catalog DECLARES (F-7f596ea3).

`slo_definitions.burn_rate_windows` (1h/5m@14.4, 6h/30m@6.0, 3d/6h@1.0) was
parsed by lib/slo/catalog.py into `SloDef.burn_rate_windows` and consumed by
nothing: `_evaluate_prom` queried a hardcoded "1h" and "6h", so the per-SLO
THRESHOLDS were never compared and the declared 3d slow-burn window never
measured. Replayed 2026-09-11: longhorn burn1h=17.95 against a declared 14.4
— computed, printed, compared to nothing.

COMMISSIONING STRAW: the pre-fix evaluator is transcribed (two literal
windows) and run against the same fake Prometheus; the 3d window is never
queried and the declared threshold breach on it is invisible. The fixed
evaluator queries every declared window and the breach is a fast-burn.

Run: python3 runbooks/tests/test-slo-declared-burn-windows.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runbooks"))
_spec = importlib.util.spec_from_file_location("slo_check", ROOT / "runbooks" / "slo-check.py")
slo_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(slo_check)
from lib.slo.catalog import BurnRateWindow, PromQuery, SloDef  # noqa: E402
from lib.slo.clients import RatioResult                        # noqa: E402
from lib.slo.calc import compute, defects                      # noqa: E402

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


# An SLO declaring windows that are NOT the hardcoded pair, so a detector
# that still queries "1h"/"6h" is visibly wrong.
SLO = SloDef(
    name="example-availability", description="", source="prom", kind="ratio",
    target=0.99, window="7d",
    prom=PromQuery(numerator="up_good", denominator="up_total"),
    burn_rate_windows=(BurnRateWindow(long="2h", short="10m", threshold=5.0),
                       BurnRateWindow(long="3d", short="6h", threshold=1.0)),
)
# Compliance per window. target 0.99 -> budget rate 0.01.
#   2h: 0.98  -> burn 2.0   (below 5.0)      10m: 1.00 -> burn 0
#   3d: 0.975 -> burn 2.5   (ABOVE 1.0)       6h: 0.97 -> burn 3.0 (still burning)
TABLE = {"7d": 0.985, "2h": 0.98, "10m": 1.0, "3d": 0.975, "6h": 0.97, "1h": 0.99}


class FakeProm:
    def __init__(self):
        self.windows: list[str] = []

    def windowed_ratio(self, q, window):
        self.windows.append(window)
        r = TABLE.get(window)
        return RatioResult(ratio=r, numerator=1.0, denominator=1.0, ok=r is not None)


def old_evaluate(slo, prom):
    """The pre-fix `_evaluate_prom`, transcribed: long window + literal 1h + 6h."""
    q = slo.prom
    long_r = prom.windowed_ratio(q, slo.window)
    short_1h = prom.windowed_ratio(q, "1h")
    short_6h = prom.windowed_ratio(q, "6h")
    return {"long_compliance": long_r.ratio, "raw_numerator": long_r.numerator,
            "raw_denominator": long_r.denominator,
            "short_compliance_1h": short_1h.ratio, "short_compliance_6h": short_6h.ratio}


print("slo declared burn windows\n")

print("-- COMMISSIONING STRAW: the hardcoded evaluator --")
prom = FakeProm()
old_raw = old_evaluate(SLO, prom)
old_snap = compute(slo_name=SLO.name, target=SLO.target, window=SLO.window, source="prom", **old_raw)
check("STRAW queries exactly the long window + 1h + 6h, never the declared 2h/10m/3d",
      set(prom.windows) == {"7d", "1h", "6h"}, str(prom.windows))
check("STRAW: the declared 3d breach is invisible (no 3d burn was computed)",
      "3d" not in old_snap.burn_rates and slo_check.fast_burns(SLO, old_snap) == [],
      str(old_snap.burn_rates))

print("\n-- the fixed evaluator --")
check("burn_window_labels returns every declared long AND short window, de-duplicated, in order",
      slo_check.burn_window_labels(SLO) == ["2h", "10m", "3d", "6h"])
prom = FakeProm()
raw = slo_check._evaluate_prom(SLO, prom)
check("queries the long window plus each declared window, and nothing hardcoded",
      set(prom.windows) == {"7d", "2h", "10m", "3d", "6h"} and "1h" not in prom.windows,
      str(prom.windows))
snap = compute(slo_name=SLO.name, target=SLO.target, window=SLO.window, source="prom", **raw)
check("snapshot carries a burn per declared window",
      set(snap.burn_rates) == {"2h", "10m", "3d", "6h"}, str(snap.burn_rates))
check("burn arithmetic: 3d compliance 0.975 vs target 0.99 -> 2.5x",
      abs(snap.burn_rates["3d"] - 2.5) < 1e-9, str(snap.burn_rates))
check("the 1h/6h COLUMNS are filled by label lookup: 6h declared -> set, 1h not declared -> None",
      snap.burn_rate_1h is None and snap.burn_rate_6h is not None
      and abs(snap.burn_rate_6h - 3.0) < 1e-9)

fb = slo_check.fast_burns(SLO, snap)
check("the declared 3d threshold (1.0) is now COMPARED: one fast burn, on 3d, still burning",
      len(fb) == 1 and fb[0]["long"] == "3d" and fb[0]["threshold"] == 1.0
      and abs(fb[0]["burn_long"] - 2.5) < 1e-9 and fb[0]["state"] == "still burning", str(fb))
check("the 2h pair (2.0x vs threshold 5.0) is not a fast burn", all(x["long"] != "2h" for x in fb))

# Threshold is the DECLARED one per SLO, not a global constant.
tight = SloDef(**{**SLO.__dict__, "burn_rate_windows": (BurnRateWindow("2h", "10m", 1.5),)})
prom = FakeProm()
snap_t = compute(slo_name=tight.name, target=tight.target, window=tight.window, source="prom",
                 **slo_check._evaluate_prom(tight, prom))
fb_t = slo_check.fast_burns(tight, snap_t)
check("a tighter declared threshold on the same data flips the 2h verdict (threshold is per-SLO)",
      len(fb_t) == 1 and fb_t[0]["long"] == "2h" and fb_t[0]["state"] == "subsided", str(fb_t))

# Missing data must not manufacture a verdict either way.
TABLE_SAVED = dict(TABLE)
TABLE["3d"] = None
prom = FakeProm()
snap_n = compute(slo_name=SLO.name, target=SLO.target, window=SLO.window, source="prom",
                 **slo_check._evaluate_prom(SLO, prom))
check("a window with no data -> burn None and no fast-burn verdict for it",
      snap_n.burn_rates["3d"] is None and all(x["long"] != "3d" for x in slo_check.fast_burns(SLO, snap_n)))
TABLE.clear(); TABLE.update(TABLE_SAVED)

print("\n-- calc compatibility --")
legacy = compute(slo_name="x", target=0.99, window="7d", source="prom", long_compliance=0.99,
                 raw_numerator=1, raw_denominator=1, short_compliance_1h=0.98, short_compliance_6h=0.99)
check("legacy 1h/6h keyword arguments still fill the columns and the map",
      abs(legacy.burn_rate_1h - 2.0) < 1e-9 and set(legacy.burn_rates) == {"1h", "6h"})
neg = compute(slo_name="x", target=0.99, window="7d", source="prom", long_compliance=0.99,
              raw_numerator=1, raw_denominator=1, short_compliances={"3d": 1.5})
check("defects() covers every declared window (a negative 3d burn is a defect)",
      any("burn_rate_3d" in d for d in defects(neg)), str(defects(neg)))

print("\n-- the script emits the finding --")
src = (ROOT / "runbooks" / "slo-check.py").read_text()
write_block = src[src.find("    if write:"):src.find("    elif args.no_write:")]
check("the write block gates on fast burns and emits a stable-titled finding",
      "fast_burns(slo, snap)" in src and "if exhausted or defective or fast:" in write_block
      and "SLO fast burn: `{s.slo_name}` over {fb['long']}" in write_block)
check("no hardcoded burn window survives in the evaluator",
      'windowed_ratio(q, "1h")' not in src and 'windowed_ratio(q, "6h")' not in src)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
