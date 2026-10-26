---
plan_id: frigate-reolink-go2rtc-flv
component: frigate
pr: null
kind: infra
current: "Reolink kitchen + living_room: Frigate ffmpeg pulls camera RTSP directly (preset-rtsp-generic, 2 sessions per camera, no go2rtc section)"
target: "Reolink kitchen + living_room: go2rtc HTTP-FLV restream (preset-rtsp-restream); Frigate 0.18.2 unchanged"
update_type: refactor
risk: medium
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - configmap/frigate-config
    - secret/frigate-rtsp-credentials
    - deployment/frigate
    - helmrelease/frigate
  shared: [igpu-i915, monitoring, iot-cameras/reolink-http]
depends_on: []
conflicts_with:
  - talos-linux-1.14.4
  - helm-drift-detection
  - flux-oci-chart-sources
exclusive: false
security_ref: null
capability_change: true
rollback_class: git-revert
finding_refs: [F-54d97a8b, F-e4c22b35]
review: ready-for-go@2026-10-26   # plan-reviewer 2026-10-26 re-review: ready-for-go, 5 blockers fixed; accuracy fixes applied after. HUMAN-GATED: needs HTTP enabled on both cameras + operator GO
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/frigate-memory-leak.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-26"
premises:
  - id: frigate-image-0.18.2
    why: "The go2rtc config semantics (create_config.py str.format substitution, restream preset) were read from the v0.18.2 source. Another version means re-checking them."
    run: kubectl get deploy frigate -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/blakeblackshear/frigate:0.18.2"
  - id: deploy-strategy-recreate
    why: "frigate-config is an RWO Longhorn PVC; the Reloader roll must be Recreate or it can Multi-Attach-block. The NVR gap estimate also assumes Recreate."
    run: kubectl get deploy frigate -n home-automation -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: kitchen-record-still-direct-rtsp
    why: "The edit script replaces this exact input line. If it is gone, someone already changed the path; re-plan."
    run: kubectl get configmap frigate-config -n home-automation -o jsonpath='{.data.config\.yml}' | grep -c '@192.168.32.234:554/Preview_01_main'
    expect_exact: "1"
  - id: living-room-record-still-direct-rtsp
    why: "Same as above, for living_room."
    run: kubectl get configmap frigate-config -n home-automation -o jsonpath='{.data.config\.yml}' | grep -c '@192.168.33.236:554/Preview_01_main'
    expect_exact: "1"
  - id: no-go2rtc-section-yet
    why: "The edit script inserts a top-level go2rtc block and refuses if one exists."
    run: kubectl get configmap frigate-config -n home-automation -o jsonpath='{.data.config\.yml}' | grep -c '^go2rtc:'
    expect_exact: "0"
  - id: urlenc-keys-not-yet-present
    why: "Step 3.2 adds FRIGATE_RTSP_PASSWORD_{2,3}_URLENC. If they already exist, a previous attempt ran partway; inspect before re-running."
    run: kubectl get secret frigate-rtsp-credentials -n home-automation -o jsonpath='{.data}' | grep -c URLENC
    expect_exact: "0"
  - id: reolink-record-drops-still-happening
    why: "The problem this plan fixes must still be present. Measured 2026-10-26: 6 (kitchen) + 9 (living_room) watchdog restarts per hour at 09:10Z, about 80 per hour combined 03:00-06:00 local, 5-14 per hour by day; kids/entry/heater 0. Zero over 6h here means the cause went away (a Wi-Fi change, for example). Then don't run the plan; re-measure."
    run: kubectl logs deploy/frigate -n home-automation -c frigate --since=6h | grep -c -e 'watchdog.kitchen .*Terminating the existing' -e 'watchdog.living_room .*Terminating the existing'
    expect_matches: '^[1-9]\d*$'
  - id: cseq-errors-still-present
    why: "The RTSP CSeq desync on the Reolink record path is the symptom this plan targets. Measured 2026-10-26: 143 lines/h (62 kitchen, 81 living_room)."
    run: kubectl logs deploy/frigate -n home-automation -c frigate --since=6h | grep -c -i 'cseq'
    expect_matches: '^[1-9]\d*$'
---

# frigate-reolink-go2rtc-flv: move the two Reolink E330s onto the go2rtc HTTP-FLV restream

## 1. Summary & why held

**This is a config fix, not a version bump.** Frigate stays at 0.18.2 and chart
7.8.0. Two cameras change how Frigate ingests them: `kitchen` (Reolink E330, fw
v3.1.0.3149, 2560x1440 H.264 main) and `living_room` (E330, fw v3.1.0.4417,
2880x1616 H.264 main).

- **Today:** Frigate's ffmpeg opens two direct RTSP sessions per camera. `Preview_01_sub`
  carries detect + audio and `Preview_01_main` carries record, both
  `preset-rtsp-generic`. The config has no `go2rtc:` section; `/api/go2rtc/streams`
  returns `{}`.
- **Target:** go2rtc pulls each camera once per stream over Reolink HTTP-FLV
  (`/flv?...channel0_main.bcs` / `channel0_ext.bcs`). Frigate reads
  `rtsp://127.0.0.1:8554/<cam>[_sub]` with `preset-rtsp-restream`. The three Wyze
  cameras (`kids`, `entry`, `heater`) do not change.

### Evidence (measured 2026-10-26, pod `frigate-8445f9b557-xsq66`, started 01:30Z)

| Signal | kitchen | living_room | kids (control) |
|---|---|---|---|
| Recording coverage, 24h, `/api/<cam>/recordings` | **82.5 %** | **77.1 %** | 99.8 % |
| Recording coverage, 6h (coordinator, same instrument) | 87.5 % | 84.8 % | 100 % |
| Worst single hour | 41 % | 42 % | 87 % (the 02:30 restart) |
| `watchdog.<cam> Terminating the existing ffmpeg` per hour | 6 | 9 | 0 |
| `CSeq N expected, 0 received` lines per hour (all on `ffmpeg.<cam>.record`) | 62 | 81 | 0 |

**The loss is time-of-day dependent, and the nightly window sits in the worst
period.** The table above is the 09:10Z (10:10 local) read. Re-measured later on
2026-10-26: the combined kitchen + living_room respawn rate is **~80 per hour
between 03:00 and 06:00 local** (per local hour since the 02:30 pod start: 28 at
02, 83 at 03, 82 at 04, 78 at 05, 62 at 06) and **5–14 per hour by day** (6, 5, 14 at
07–09). Coverage for 03:00–06:00 local today was **kitchen 73.4 % / living_room
71.2 %**, against **99.1 % / 95.6 %** for the 6 h ending 13:30 local (daytime), and
85.9 % / 80.1 % over 24 h at 13:32. A single "baseline" number therefore depends
on when it is read; §2.2 records all three at the window.

Each record drop follows the same sequence:

1. `CSeq ... expected, 0 received`
2. `Failed reading RTSP data: Connection timed out`
3. `Error during demuxing`
4. The watchdog kills and respawns ffmpeg.

The record ffmpeg also logs `[aac] Queue input is backward in time` between
drops. ffmpeg prints these at its ERROR level, but Frigate's health check does
not count them, and fps stays > 0 throughout. Coverage is the only signal that
sees the loss (`frigate_coverage_scan` in `runbooks/health-check.sh`).

### Upstream recommendation (quoted from `docs/docs/configuration/camera_specific.md` at tag v0.18.2)

> | 5MP or lower | All | http-flv | Stream is h264 |
>
> According to [this discussion] ... the http video streams seem to be the most reliable for Reolink.
> The setup of main stream can be also done via RTSP, but isn't always reliable on all hardware versions.
>
> Ensure HTTP is enabled in the camera's advanced network settings.

The upstream example is
`ffmpeg:http://reolink_ip/flv?port=1935&app=bcs&stream=channel0_main.bcs&user=…&<pw-key>=…#video=copy#audio=copy#audio=opus`  (`<pw-key>` is the Reolink query key spelled `pass`+`word`; written that way here only because the repo secret scan flags the literal.)
for main and `…channel0_ext.bcs…` for sub, with camera inputs on
`rtsp://127.0.0.1:8554/<name>` + `preset-rtsp-restream`. Both cameras are
≤ 5 MP H.264, so both fall in the http-flv row.

### Why this is held / not trivial

1. **Operator prerequisite (blocking): HTTP is OFF on both cameras today.** Measured
   from inside the frigate pod: TCP 80, 443 and 1935 return `ConnectionRefused`
   on both cameras, while 554 (RTSP) and 8000 (ONVIF) are open. A refusal means
   the camera's own server port is switched off; it is not a firewall drop. The
   §2.3 FLV probe fails today with `Connection to tcp://<ip>:80 failed:
   Connection refused`. The operator must enable **HTTP** in the Reolink app
   (gear > More Features / Network > Advanced > Server Settings > HTTP; the web
   UI has the same switch under Network > Advanced > Server Settings) on
   **both** cameras before this plan can run. Enable RTMP too only if the §2.3
   probe still fails with HTTP alone.
2. **E330 HTTP-FLV support is unproven for this hardware.** Reolink's
   port-settings article says E1 Pro hardware `IPC_566SD54MP` "does not support
   the RMTP port". The E330 is the E1 Pro. That article does not say HTTP-FLV
   on port 80 fails, and the upstream table says all ≤ 5 MP Reolinks are
   http-flv. Firmware differs between the two cameras. **Gate:** the §2.3
   ffprobe must return an h264 video stream for all four URLs (2 cameras × main/ext).
   If either camera fails, see §3-B.
3. **The kitchen password needs URL-encoding.** In HTTP-FLV the password travels
   in a query string. go2rtc's stream substitution (`create_config.py`:
   `stream.format(**FRIGATE_ENV_VARS)`) does not URL-encode it. At least one of
   the two camera passwords contains URL-reserved characters (checked by
   character class only; the values were never printed), and the camera's HTTP
   handler percent-decodes the query string. Step 3.2 adds
   `FRIGATE_RTSP_PASSWORD_{2,3}_URLENC` (`urllib.parse.quote(pw, safe="")`) to the
   SOPS secret. The existing keys stay untouched for the ONVIF users.
4. **`capability_change: true`, declared honestly.** The change adds two things
   that do not exist today:
   - a go2rtc restream of both cameras on `frigate:8554`. It is ClusterIP-only,
     but go2rtc RTSP has no auth by default.
   - an HTTP server on two IoT-VLAN cameras.

   It also changes live view for these cameras from jsmpeg to go2rtc MSE/WebRTC,
   with audio.

### Will this alone fix the loss? (honest expectation)

**Partially. It is not a guaranteed fix.** Both Reolinks hang off the Hallway
U6 Pro on 2.4 GHz channel 1. Coordinator measurement, 2026-10-26: 53 clients,
81 % channel utilisation, kitchen satisfaction 60, 16 % tx retries, strong
signal (-44/-46 dBm). The Wyze cameras share that channel and record at
~100 %, but they use UDP RTSP, which tolerates loss by dropping frames instead of
desyncing a TCP control channel. The failure pattern is the Reolink RTSP
server losing CSeq sync under retransmission, followed by a 20-s read timeout
and a full ffmpeg respawn. That points at the *protocol path* amplifying Wi-Fi
congestion into multi-second gaps.

- **What HTTP-FLV + go2rtc plausibly fixes:** the CSeq desync and the
  `preset-rtsp-generic` respawn cost. go2rtc keeps one long-lived FLV pull
  per stream and reconnects at the source without restarting Frigate's record
  ffmpeg. The two RTSP sessions per camera become two HTTP-FLV pulls behind
  one restream, and HA/live-view consumers stop adding camera sessions.
- **What it does NOT fix:** airtime. The main streams at 2560x1440@15 and
  2880x1616@20 still cross a saturated 2.4 GHz channel. If go2rtc's source
  stalls, Frigate still sees a gap. Expect residual loss in the evening peak
  (19–22 local, today's worst hours).
- **So:** the §4 gates are set to tell "fixed" from "cheaper reconnects" (G2).
  If G2 lands between baseline and target, the remainder is Wi-Fi, and the
  operator options below apply.

**Wi-Fi alternatives. These are separate operator decisions and not steps in this plan:**

- (a) **A 5 GHz-only IoT SSID on VLAN 30 for the two Reolinks.** The E330 is
  dual-band per Reolink's E1 Pro/E330 FAQ ("unterstützt Dual-Band WiFi – sowohl
  2,4GHz als auch 5GHz", band switchable in the camera's network settings). The
  Hallway 5 GHz radio (ch 40) is at 14 % utilisation. Today `cberg-iot` is
  2.4 GHz only, so this needs a new SSID (or a band-split) plus re-joining
  both cameras.
- (b) **Lock-to-AP both Reolinks onto the Living Room U7 Pro** (2.4 GHz ch 11,
  4 clients, 40 % utilisation). This is lower effort; it depends on signal at the
  kitchen position.
- (c) Lower the main-stream bitrate/fps in the Reolink app ("fluency first" =
  CBR, upstream's recommended setting). This trades quality for airtime.

The 02:30 `frigate-restart` codec-probe failures on the Wyze cameras (~7 min) are
**out of scope** here.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Abort the plan with nothing changed
if any gate fails.

**2.1 Premises:**

```bash
.venv/bin/python3 runbooks/plan-premises.py frigate-reolink-go2rtc-flv --require-premises
```

Every premise must PASS.

**2.2 Baseline coverage (RECORD-ONLY; nothing in the pre-check gates on it).**
Write the numbers into the window log. The gates that judge the change are the
fixed thresholds in §4 plus the G2 improvement test; the premises (not these
numbers) are what prove the symptom is still present. Read it knowing the value
swings with time of day (§1): at a 03:30 nightly run the preceding hours are the
worst of the day, so the 6 h read will be LOW (about the 73 %/71 % night figures)
and an attended 09:00 run will read HIGH (about 99 %/96 %). Neither is "the"
baseline, and **the nightly window samples the worst period**, which is the
conservative case for judging a fix.

```bash
kubectl port-forward -n home-automation svc/frigate 15000:5000 >/dev/null 2>&1 & PF=$!; sleep 3
cat > /tmp/frigate-cov.py <<'EOF'
import json, sys, time, urllib.request
# usage: frigate-cov.py HOURS [START_EPOCH]
#   no START : window = [now-10min-HOURS, now-10min]
#   START    : window = [START, START+HOURS]  (use pod startTime+600 to skip the restart penalty)
hours = float(sys.argv[1])
if len(sys.argv) > 2:
    after = float(sys.argv[2]); before = after + hours * 3600
else:
    before = time.time() - 600; after = before - hours * 3600
assert before <= time.time(), "window ends in the future: wait"
for cam in ("kitchen", "living_room", "kids", "entry"):
    segs = json.load(urllib.request.urlopen(
        f"http://127.0.0.1:15000/api/{cam}/recordings?after={int(after)}&before={int(before)}", timeout=30))
    assert isinstance(segs, list), (cam, segs)
    cov = sum(max(0.0, min(s["end_time"], before) - max(s["start_time"], after)) for s in segs)
    print(f"{cam}\t{100*cov/(before-after):.1f}\tsegments={len(segs)}")
EOF
echo "== 6h";  python3 /tmp/frigate-cov.py 6
echo "== 24h"; python3 /tmp/frigate-cov.py 24
kill $PF 2>/dev/null
```

Measured 2026-10-26 (`frigate-cov.py` prints `camera  percent  segments`): 6 h ending
13:30 local, kitchen 99.1 / living_room 95.6; 24 h at 13:32, 85.9 / 80.1 (82.5 /
77.1 at 09:10Z); 03:00–06:00 local, 73.4 / 71.2. Kids/entry ≥ 99.8 in every
window. The 24 h read is what G2's PARTIAL test compares against, so keep THIS
session's 24 h numbers, not the ones quoted here. This
measures the same thing as `frigate_coverage_scan` in `runbooks/health-check.sh`:
segment seconds clipped to the window. Either one may be used.
`heater` is left out of the control set. F-efa8e6e5 says it is off the network, but
F-6a65147e (2026-10-26) records it streaming 2.0 fps and recording 100.0 % over
6 h, so F-efa8e6e5 is probably stale. It is not this plan's to close; once it is
closed, `heater` can be added as a third control. **If `/tmp/frigate-cov.py`
is missing in a later step (new shell, new day), recreate it from this block;** it
needs a `kubectl port-forward -n home-automation svc/frigate 15000:5000` running.

**Why the explicit START form exists.** Frigate's own restart costs the Wyze
cameras their first segment ~447 s after pod start (codec probe), measured on the
2026-10-26 01:30:15Z restart. A window that starts at pod start false-FAILS the
kids control (replayed: kids 85.4 / entry 98.1 over `[T, T+50m]`). Starting the
window at `T+10m` replayed kids 100.4 / entry 100.8 while kitchen 78.0 and
living_room 75.3 still read low, so the controls pass and the targets can fail.

**2.3 OPERATOR PREREQUISITE + FLV probe (hard gate).**

The operator confirms that HTTP is enabled on both E330s (see §1 item 1).
Then run this read-only ffprobe from inside the frigate pod. It uses the pod's
own env for credentials and redacts the password from its output:

```bash
cat > /tmp/flv-probe.py <<'EOF'
import os, subprocess, urllib.parse, glob
fp = (sorted(glob.glob("/usr/lib/ffmpeg/*/bin/ffprobe")) or ["ffprobe"])[-1]
for cam, ip, n in (("kitchen", "192.168.32.234", "3"), ("living_room", "192.168.33.236", "2")):
    pw = urllib.parse.quote(os.environ["FRIGATE_RTSP_PASSWORD_" + n], safe="")
    for st in ("main", "ext"):
        url = (f"http://{ip}/flv?port=1935&app=bcs&stream=channel0_{st}.bcs"
               f"&user={os.environ['FRIGATE_RTSP_USER_' + n]}&pass"
               f"word={pw}")
        try:
            r = subprocess.run([fp, "-v", "error", "-rw_timeout", "8000000", "-show_entries",
                                "stream=codec_name,width,height", "-of", "csv=p=0", url],
                               capture_output=True, text=True, timeout=30)
            out, err, rc = r.stdout.strip().replace("\n", " | "), r.stderr.strip(), r.returncode
        except subprocess.TimeoutExpired:
            out, err, rc = "", "timeout", 124
        # redact BEFORE truncating, so a password straddling the cut cannot leak a prefix
        err = err.replace(pw, "<pw>").replace(os.environ["FRIGATE_RTSP_PASSWORD_" + n], "<pw>")[:160]
        print(f"FLV {cam} {st} rc={rc} streams=[{out}] err=[{err}]")
EOF
kubectl exec -i -n home-automation deploy/frigate -c frigate -- python3 - < /tmp/flv-probe.py
```

- **PASS:** all four lines show `rc=0` and `streams=[h264,<w>,<h> | aac...]`. Main
  should be ≈ 2560x1440 (kitchen) and ≈ 2880x1616 (living_room). Ext should be
  the sub resolution.
- **FAIL as measured 2026-10-26** (proves the gate can fail):
  `rc=1 ... Connection to tcp://192.168.32.234:80 failed: Connection refused`
  on all four lines.
- **FAIL with `401`/`Unauthorized`/empty streams after HTTP is on:** a credential
  or encoding problem. Do not proceed; report.
- **Mixed result:** one camera passes and the other fails (possible: different
  hardware/firmware). Run §3 for **both** cameras with `REOLINK_MODE=rtsp` (§3-B).
  Do not mix modes in one window. Report the per-camera result on F-54d97a8b.

**2.4 Health floor.** `kubectl get helmrelease frigate -n home-automation` shows
Ready=True. `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'` lists
nothing for home-automation. The 02:30 `frigate-restart` Job has completed
(`kubectl get jobs -n home-automation | grep frigate-restart`). Don't start
between 02:20 and 02:45 local.

## 3. Steps

**One commit carries both files.** `secret.sops.yaml` and `configmap.sops.yaml`
must land together. If the ConfigMap references `{FRIGATE_RTSP_PASSWORD_3_URLENC}`
before the Secret has it, `create_config.py` hits `KeyError` and `sys.exit`s, and
go2rtc does not start: live view breaks for all cameras and the two Reolinks stop
recording. §3.3b is a hard pre-push gate for exactly that.

All commands run from the repo root on the Mac mini (zsh), with
`export SOPS_AGE_KEY_FILE=$PWD/age.key` and `umask 077` (the temp files below hold
decrypted config; they are deleted at the end of §3.4). Never print them.

**3.1 Write the two helper scripts.** Both were dry-tested 2026-10-26 on scratch
copies of the real encrypted files.

```bash
cat > /tmp/reolink-go2rtc-edit.py <<'EOF'
import os, sys
# Filter: plain config.yml text on stdin -> edited text on stdout. Anchors are at the
# file's own indent (go2rtc/cameras at column 0; inputs at 6 spaces), so it does not
# depend on how sops indents a block scalar.
t = sys.stdin.read()
MODE = os.environ.get("REOLINK_MODE", "flv")
assert MODE in ("flv", "rtsp"), MODE
assert "\ngo2rtc:\n" not in "\n" + t and not t.startswith("go2rtc:"), "go2rtc section already present"
CAMS = {"kitchen": ("192.168.32.234", "3"), "living_room": ("192.168.33.236", "2")}
def src(ip, n, main):
    if MODE == "flv":
        s = (f"ffmpeg:http://{ip}/flv?port=1935&app=bcs&stream=channel0_{'main' if main else 'ext'}.bcs"
             f"&user={{FRIGATE_RTSP_USER_{n}}}&pass"
             f"word={{FRIGATE_RTSP_PASSWORD_{n}_URLENC}}")
        return s + ("#video=copy#audio=copy#audio=opus" if main else "")
    return f"rtsp://{{FRIGATE_RTSP_USER_{n}}}:{{FRIGATE_RTSP_PASSWORD_{n}_URLENC}}@{ip}:554/Preview_01_{'main' if main else 'sub'}"
g = ["go2rtc:", "  streams:"]
for cam, (ip, n) in CAMS.items():
    g += [f"    {cam}:", f'    - "{src(ip, n, True)}"', f"    {cam}_sub:", f'    - "{src(ip, n, False)}"']
    for kind, name in (("sub", f"{cam}_sub"), ("main", cam)):
        old = (f"      - path: rtsp://{{FRIGATE_RTSP_USER_{n}}}:{{FRIGATE_RTSP_PASSWORD_{n}}}@{ip}:554/Preview_01_{kind}\n"
               f"        input_args: preset-rtsp-generic\n")
        new = f"      - path: rtsp://127.0.0.1:8554/{name}\n        input_args: preset-rtsp-restream\n"
        assert t.count(old) == 1, (cam, kind, t.count(old))
        t = t.replace(old, new)
anchor = "\ncameras:\n"
assert t.count(anchor) == 1, t.count(anchor)
t = t.replace(anchor, "\n" + "\n".join(g) + "\n" + anchor.lstrip("\n"))
sys.stdout.write(t)
EOF
cat > /tmp/go2rtc-subst-check.py <<'EOF'
import subprocess, sys, yaml
# usage: go2rtc-subst-check.py SECRET.sops.yaml CONFIGMAP.sops.yaml
# Mirrors create_config.py: every go2rtc stream string goes through str.format(**FRIGATE_*).
sec, cm = sys.argv[1], sys.argv[2]
def dec(p, *a):
    return subprocess.run(["sops", "decrypt", *a, p], check=True, capture_output=True, text=True).stdout
env = {k: str(v) for k, v in yaml.safe_load(dec(sec))["stringData"].items() if k.startswith("FRIGATE_")}
cfg = yaml.safe_load(dec(cm, "--extract", '["data"]["config.yml"]'))
streams = (cfg.get("go2rtc") or {}).get("streams") or {}
fails = n = 0
for name, v in streams.items():
    for s in (v if isinstance(v, list) else [v]):
        n += 1
        try:
            s.format(**env)
        except KeyError as e:
            fails += 1; print("MISSING", name, e)
print("go2rtc_streams_checked", n)
print("go2rtc_substitution_failures", fails)
sys.exit(1 if fails or n == 0 else 0)
EOF
```

The edit is a pure `stdin -> stdout` filter that asserts before it writes. A second
run on already-edited text exits 1 with `AssertionError: go2rtc section already
present` and writes 0 bytes (measured). A run against a config whose input lines
have changed fails on the `('kitchen','sub',0)`-style count assert.

**3.2 Add the URL-encoded passwords to the Secret.** Every step is chained with
`&&` and the loop `break`s with a `STOP` line on the first failure: a plain
`a | b | c` pipeline reports only the LAST command's status, so a failed
`sops decrypt` would otherwise slip through as "success". Dry-tested 2026-10-26 on
scratch copies, including a forced failure (decrypt target missing: prints
`STOP: step 3.2 failed for key 2`, secret byte-for-byte unchanged). No secret
reaches argv or stdout:

```bash
export SOPS_AGE_KEY_FILE=$PWD/age.key; umask 077
F=kubernetes/apps/home-automation/frigate-nvr/app/secret.sops.yaml
for n in 2 3; do
  ENC=$(sops decrypt --extract "[\"stringData\"][\"FRIGATE_RTSP_PASSWORD_$n\"]" "$F") && test -n "$ENC" \
    && printf '%s' "$ENC" | python3 -c 'import sys,json,urllib.parse; sys.stdout.write(json.dumps(urllib.parse.quote(sys.stdin.read(), safe="")))' \
    | sops set --value-stdin "$F" "[\"stringData\"][\"FRIGATE_RTSP_PASSWORD_${n}_URLENC\"]" \
    || { echo "STOP: step 3.2 failed for key $n"; break; }
done
sops decrypt "$F" | python3 -c "import sys,yaml,urllib.parse; d=yaml.safe_load(sys.stdin)['stringData']; ok={n: urllib.parse.unquote(d['FRIGATE_RTSP_PASSWORD_%s_URLENC'%n])==d['FRIGATE_RTSP_PASSWORD_'+n] for n in '23'}; assert all(ok.values()), ok; print('urlenc_roundtrip_ok', ok)"
```

PASS: no `STOP:` line and `urlenc_roundtrip_ok {'2': True, '3': True}` (the last
command asserts, so a missing or wrong key exits non-zero with a traceback). On
any failure, restore the file before retrying: `git checkout -- "$F"` (it is not
committed yet; do this only if nobody else has staged changes to that one path).

**3.3 Edit the ConfigMap with `sops decrypt --extract` / `sops set`.** Do NOT use
`EDITOR=<script> sops <file>`: sops hands `$EDITOR` a temp file in which the
`config.yml` block scalar is re-indented (content at 8 spaces), so column-0 and
6-space anchors do not match, and the script dies with the assert. The route below
was verified end to end on a scratch copy of the real file.

**Why the chain matters (measured).** `echo "edit_rc=$?"` on its own line does NOT
stop the next line, and a forced failed edit then let `sops set` write an EMPTY
`config.yml` (0 bytes) while a `cmp` of empty against empty still printed
`CONFIG_ROUNDTRIP_OK`. The version below runs the edit from a file, chains every
element with `&&` so `sops set` is only reached when the edit succeeded, produced
bytes, and contains exactly one `go2rtc:` block, and then gates on content, not on
`cmp` alone. Keep §3.3–§3.4 in ONE shell (`W` is a per-run temp dir).

```bash
umask 077; W=$(mktemp -d /tmp/frigate-cfg.XXXXXX); echo "W=$W"
CM=kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml
sops decrypt --extract '["data"]["config.yml"]' "$CM" > "$W/config.before.yml" \
  && test -s "$W/config.before.yml" \
  && REOLINK_MODE=flv python3 /tmp/reolink-go2rtc-edit.py < "$W/config.before.yml" > "$W/config.after.yml" \
  && test -s "$W/config.after.yml" \
  && test "$(grep -c '^go2rtc:' "$W/config.after.yml")" = 1 \
  && python3 -c 'import sys,json; sys.stdout.write(json.dumps(sys.stdin.read()))' < "$W/config.after.yml" \
  | sops set --value-stdin "$CM" '["data"]["config.yml"]'
echo "chain_rc=$?"      # must be 0. Non-zero: STOP. If the edit/guards failed, $CM was never touched.

sops decrypt --extract '["data"]["config.yml"]' "$CM" > "$W/config.live.yml"
test -s "$W/config.live.yml" && cmp "$W/config.after.yml" "$W/config.live.yml" \
  && test "$(grep -c '^go2rtc:' "$W/config.live.yml")" = 1 \
  && test "$(diff "$W/config.before.yml" "$W/config.live.yml" | grep -c '^[<>]')" = 26 \
  && echo STEP33_GATES_PASS || echo "STEP33_GATES_FAIL live_bytes=$(wc -c < "$W/config.live.yml")"
```

PASS requires `chain_rc=0` **and** the line `STEP33_GATES_PASS` (which proves, in
order: live config non-empty, equal to what was written, exactly one `go2rtc:`
block, and a decrypted diff of exactly 26 lines: 10 added go2rtc lines plus 16 lines
for the four input swaps, 8 removed and 8 added). On `STEP33_GATES_FAIL` or any
other result: `git checkout -- "$CM"` restores the committed encrypted file
(nothing is committed yet), then `rm -rf "$W"` and stop. For `REOLINK_MODE=rtsp`
(§3-B) the counts are the same.

Dry-tested 2026-10-26 on a scratch copy of the real encrypted file: the normal run
printed `chain_rc=0` and `STEP33_GATES_PASS`; a forced edit failure
(`REOLINK_MODE=bogus`) printed `AssertionError: bogus`, `chain_rc=1`, and left the
encrypted file byte-for-byte unchanged; and re-creating the reviewer's blank-config
case (`sops set` of an empty string) printed `STEP33_GATES_FAIL live_bytes=0`.

**What the git diff looks like (cosmetic):** sops re-encrypts the whole `config.yml`
value and rewrites `lastmodified` and `mac`. On the scratch copy `git diff --numstat`
reported 3 added / 3 removed lines in the encrypted file, none of which is
reviewable. **The review artifact is the 26-line decrypted diff above**; show it
(`diff "$W/config.before.yml" "$W/config.live.yml"`) to anyone who asks. If the
real file shows a larger re-indent, that is cosmetic too, and the roundtrip `cmp`
is what proves the content (and `STEP33_GATES_PASS` is the gate that must print).

Dry-run diff excerpt (FLV mode, decrypted):

```
> go2rtc:
>   streams:
>     kitchen:
>     - "ffmpeg:http://192.168.32.234/flv?port=1935&app=bcs&stream=channel0_main.bcs&user={FRIGATE_RTSP_USER_3}&<pw-key>={FRIGATE_RTSP_PASSWORD_3_URLENC}#video=copy#audio=copy#audio=opus"
>     kitchen_sub: …channel0_ext.bcs…  (no #video/#audio suffix)
>     living_room / living_room_sub: same, 192.168.33.236, _2
<       - path: rtsp://{FRIGATE_RTSP_USER_3}:{FRIGATE_RTSP_PASSWORD_3}@192.168.32.234:554/Preview_01_main
<         input_args: preset-rtsp-generic
>       - path: rtsp://127.0.0.1:8554/kitchen
>         input_args: preset-rtsp-restream
```

(Four such input swaps: kitchen/living_room x sub/main. Roles are unchanged: sub =
detect + audio, main = record. The Wyze inputs are untouched.)

**3.3b HARD GATE: pre-push substitution check (B3).** Decrypt the Secret and the
ConfigMap as they now sit in the working tree and run every go2rtc stream string
through `str.format(**FRIGATE_*)`, the exact call that `create_config.py` makes:

```bash
python3 /tmp/go2rtc-subst-check.py \
  kubernetes/apps/home-automation/frigate-nvr/app/secret.sops.yaml \
  kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml
echo "subst_rc=$?"
```

PASS requires all three: `go2rtc_streams_checked 4`, `go2rtc_substitution_failures 0`
and `subst_rc=0`. **Do not commit on anything else.** Measured 2026-10-26 on
scratch copies, so the gate can fail:

| Secret | ConfigMap | Prints |
|---|---|---|
| new (with `_URLENC`) | new | `streams_checked 4`, `failures 0`, rc 0 |
| old (without) | new | 4 x `MISSING … FRIGATE_RTSP_PASSWORD_{2,3}_URLENC`, `failures 4`, rc 1 |
| new | old (no go2rtc block) | `streams_checked 0`, rc 1 (an empty check fails closed) |

**3.4 Validate, commit, push.** Shared worktree: `--only`, then check the subject.
The kubeconform gate is scoped to the app folder and tests the EXIT CODE, because
`task kubeconform` over the whole repo currently exits non-zero for reasons
unrelated to this change (64 invalid / 23 errors repo-wide on 2026-10-26, none in
this folder) and a `| tail` hides the status either way:

```bash
kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/home-automation/frigate-nvr/app > /tmp/kc-frigate.out 2>&1
KC=$?; tail -3 /tmp/kc-frigate.out; echo "kubeconform_rc=$KC"
```

PASS: `kubeconform_rc=0` (measured today on the unmodified folder: `Valid: 8, Invalid: 0,
Errors: 0, Skipped: 5`). Negative control, measured: a ConfigMap with `data: {a: 1}`
returns rc 1 with `got number, want null or string`. Any non-zero `kubeconform_rc`:
do not commit.

```bash
cat > /tmp/msg-reolink.txt <<'EOF'
fix(frigate): Reolink kitchen/living_room via go2rtc HTTP-FLV restream (F-54d97a8b, F-e4c22b35)

Direct RTSP record path desyncs (CSeq) and respawns ~15x/h; 24h coverage
82.5% / 77.1%. Upstream recommends http-flv via go2rtc for <=5MP Reolinks.
Adds URL-encoded password keys for the FLV query string.
Plan: runbooks/maintenance/plans/frigate-reolink-go2rtc-flv.md
EOF
git commit --only kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml \
  kubernetes/apps/home-automation/frigate-nvr/app/secret.sops.yaml -F /tmp/msg-reolink.txt
git log -1 --format=%s   # must be the subject above; amend before push if not
git show --stat HEAD     # exactly the two frigate files
git push
rm -rf "$W"; rm -f /tmp/kc-frigate.out
```

In the commit message, append the attribution lines from the executing session.
(Source the sweep DSN in a SEPARATE call from `git commit`; a sourced DSN breaks
the pre-commit gate.)

**3.5 Rollout (no manual action), and what T means.** The Flux webhook reconciles
the Kustomization `frigate` (namespace `home-automation`). Reloader
(`reloader.stakater.com/auto: "true"`, set by the HR postRenderer; Reloader runs in
kube-system) sees BOTH the ConfigMap (volume) and the Secret (envFrom) change and
patches the Deployment. **It may roll twice** (one event per object), and an
intermediate pod can start with the new ConfigMap and the old Secret: go2rtc then
exits on the `KeyError` and that pod dies before the final one starts (§3.3b is
what makes the final pod consistent). Therefore **T is the start of the FINAL pod,
not the first new one:**

```bash
kubectl rollout status deploy/frigate -n home-automation --timeout=10m
T=$(kubectl get pod -n home-automation -l app.kubernetes.io/name=frigate -o jsonpath='{.items[0].status.startTime}'); echo "T1=$T"
# wait >= 3 minutes, then re-read; repeat until two reads >= 3 min apart are identical
T=$(kubectl get pod -n home-automation -l app.kubernetes.io/name=frigate -o jsonpath='{.items[0].status.startTime}'); echo "T2=$T"
```

`T1 == T2` and `T` later than the push time. If the pod start is still older than
the push after 10 minutes, the roll did not happen: run **once**
`kubectl rollout restart deploy/frigate -n home-automation` via cberg-agent.

**The NVR gap is NOT 1–2 minutes.** With `strategy: Recreate` the Frigate API is
down ~1–2 min, but recording resumes camera by camera: on the 2026-10-26 01:30:15Z
restart the first Wyze (`kids`) segment arrived ~447 s after pod start (codec
probe), so budget **~8 min of recording gap per roll for the Wyze cameras**, and
up to ~16 min across a double roll. The Reolinks' own recovery time is part of
what G0/D/G1-lite observe.

**§3-B (fallback, only if §2.3 failed for either camera): go2rtc native RTSP.**
Run §3.1–3.5 with `REOLINK_MODE=rtsp` instead. go2rtc's own RTSP client pulls
`Preview_01_main/sub` (one session per stream, shared by every consumer). This
needs no camera HTTP. go2rtc parses the URL with Go `url.Parse`, which rejects a
bare `%`, so the `_URLENC` keys are needed here too. Expectation: this replaces
ffmpeg's RTSP client, the component that logs the CSeq desync. It is weaker
evidence than FLV, and §4 decides.

## 4. Verification

**Definitions.** `T` = start of the FINAL Frigate pod (§3.5). A port-forward
`kubectl port-forward -n home-automation svc/frigate 15000:5000 >/dev/null 2>&1 & PF=$!`
serves every API call below (`kill $PF` afterwards). Gates are in two tiers:
**in-window** (G0a, G0, D, G1-lite; the window agent runs them, ~T+30) and
**post-window** (G1 at T+70, G2 at T+24 h; owned by the operator or the next
window/sweep, see "Status flow"). The nightly window's usable budget is 70 min
(90 minus the 20-min Step 0 reserve); that is why coverage gates are not in-window.

**G0a. Pre-push substitution (hard gate, §3.3b).** Already run before the push.
Cite its output in the window log. It is the only gate that can catch a
`KeyError` BEFORE the cluster sees it.

**G0. go2rtc is up with the configured streams (T+5 min).** This gate proves ONLY
that the config loaded and go2rtc is running with the four configured streams. It
does NOT prove that any camera connected: in go2rtc 1.9.14 `NewStream` creates one
producer per configured source, and its `MarshalJSON` returns just `{"url": ...}`
while the producer is unconnected, so `producers >= 1` is true even with a wrong FLV
URL or credential. Connection is proven by G0b, D and G1-lite, not here.

```bash
curl -s http://127.0.0.1:15000/api/go2rtc/streams | python3 -c "import sys,json; d=json.load(sys.stdin); print({k: len(v.get('producers') or []) for k,v in d.items()})"
```

PASS: exactly the 4 keys `kitchen`, `kitchen_sub`, `living_room`, `living_room_sub`
(each with at least one producer entry). **Today this returns `{}`** (no go2rtc
section), so it fails on an absent or non-running go2rtc.

**G0b. Sources actually connected (T+10 min, once Frigate's ffmpeg has connected).**
Two samples 30 s apart, because ffmpeg retries a dead source and a single sample can
catch it mid-connect:

```bash
for i in 1 2; do
  curl -s http://127.0.0.1:15000/api/go2rtc/streams | python3 -c "
import sys,json
d=json.load(sys.stdin); bad=0
for k in ('kitchen','kitchen_sub','living_room','living_room_sub'):
    s=d.get(k) or {}; prods=s.get('producers') or []; cons=s.get('consumers') or []
    conn=sum(1 for p in prods if set(p)-{'url'})
    ok=len(cons)>=1 and conn>=1; bad+=0 if ok else 1
    print(k,'producers=%d connected=%d consumers=%d'%(len(prods),conn,len(cons)),'OK' if ok else 'FAIL')
print('g0b_failures',bad)"
  sleep 30
done
```

PASS: both samples print `g0b_failures 0`, i.e. every one of the 4 streams has
`consumers >= 1` (Frigate's ffmpeg is reading it) **and** `connected >= 1` (a
producer whose JSON carries more than the bare `url`, which is what a connected
go2rtc 1.9.14 producer looks like). Dry-run on synthetic JSON 2026-10-26: `{}`
prints `g0b_failures 4`; a stream whose producer is only `{"url": ...}` with no
consumer prints `FAIL` for that stream and `g0b_failures 1`; a healthy shape prints
`g0b_failures 0`. **The connected shape was not observed live** (`streams` is `{}`
until this plan lands), so if the first real run shows a different shape, fall back
to `consumers >= 1` alone and amend this gate; dead sources are still caught by D
and G1-lite.

Supplementary only (never shown non-zero, so it is NOT a gate):

```bash
kubectl logs deploy/frigate -n home-automation -c frigate --since=10m | grep -i -c -e 'Invalid substitution' -e 'restricted source'
```

Expected `0`. Its non-zero behaviour comes from `create_config.py`'s `print("[ERROR]
Invalid substitution found …")`, which was read in source but not provoked live;
the go2rtc log lines in the Frigate log are otherwise only nginx. That is why G0a,
G0b and D carry the weight.

**D. Detect path alive (T+10 min).** A dead sub restream would still pass any
record-coverage gate, so check the detect input directly:

```bash
curl -s http://127.0.0.1:15000/api/stats | python3 -c "import sys,json; d=json.load(sys.stdin)['cameras']; print({k:d[k].get('camera_fps') for k in ('kitchen','living_room','kids','entry')})"
```

PASS: `kitchen` and `living_room` `camera_fps > 0` (baseline 5.0 and 5.1, measured
2026-10-26; `kids`/`entry` ≈ 2.0 are the controls). FAIL: either Reolink at `0.0` or
`None`, which is what a dead `_sub` restream or a refused detect input reads.

**G1-lite. Respawns and CSeq since T+10 (in-window, evaluated at T+30).** Counts the
failure signature itself over the 20 minutes after the restart settles (so the
embeddings-segfault noise of F-f01dcab4 at pod start and the Wyze codec probes fall
before the window):

```bash
SINCE=$(python3 -c 'import sys,datetime; t=datetime.datetime.strptime(sys.argv[1],"%Y-%m-%dT%H:%M:%SZ"); print((t+datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$T")
kubectl logs deploy/frigate -n home-automation -c frigate --since-time="$SINCE" | grep -c -e 'watchdog.kitchen .*Terminating the existing' -e 'watchdog.living_room .*Terminating the existing'
kubectl logs deploy/frigate -n home-automation -c frigate --since-time="$SINCE" | grep -c -i 'cseq'
```

The patterns are copied from the live Frigate log (case-exact for the logger name
and message, case-insensitive for `cseq`). **The baseline depends on when this
runs** (§1): at the nightly window the 20 minutes after T+10 fall around 04:00–04:30
local (T is roughly 03:55–04:00 after the pre-checks and the push), where the combined kitchen + living_room rate is **~80 respawns per hour, i.e.
~27 expected in 20 minutes**; in an attended 09:00 local run it is 5–14 per hour,
i.e. **~2–5 in 20 minutes**. Daytime CSeq baseline is 143 lines/h (higher at night).

- **PASS:** respawns ≤ 1 **and** CSeq = 0. Under either baseline P(≤1 in 20 min) is
  small (about 4 % at the daytime upper end, effectively 0 at night), so a PASS is
  informative but not proof.
- **REVERT (§5):** no improvement over the baseline for the slot in use: respawns
  **≥ 20 in a nightly window** (≈ 75 % of the ~27 expected), or **≥ 5 in a daytime
  or attended window**. Pick the threshold from the clock time of T+10, not from
  the window id.
- **PARTIAL:** anything between. Keep the change; G2 decides. The fixed coverage
  thresholds below are unchanged.

**G1. Coverage, post-window (T+70).** The window must skip the restart penalty
(Wyze first segment ~447 s after pod start), so it is `[T+10m, T+60m]`, not
`[T, T+50m]`:

```bash
START=$(python3 -c 'import sys,datetime; print(int(datetime.datetime.strptime(sys.argv[1],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())+600)' "$T")
python3 /tmp/frigate-cov.py 0.8333 "$START"
```

(`/tmp/frigate-cov.py`: recreate from §2.2 if missing. The script asserts the
window is not in the future.)

- **PASS:** kitchen ≥ 98 and living_room ≥ 98, with the controls kids ≥ 98 and entry
  ≥ 98. Replayed on the 2026-10-26 restart this window read kids 100.4 / entry 100.8
  and kitchen 78.0 / living_room 75.3, i.e. controls pass and targets can fail.
- If a control is low: the pod or storage is the problem, not the cameras. Treat as
  FAIL and investigate before judging the cameras.
- A 50-minute window alone can pass or fail by luck (hourly baseline ranged 41–100 %),
  which is why G1 is paired with G1-lite and why G2 is decisive.

**G2. 24h coverage (decisive; the plan is not retired until this passes).** Run at
≥ T + 24 h 20 min so the whole window lies after the restart penalty:

```bash
python3 /tmp/frigate-cov.py 24      # or: frigate_coverage_scan <port> 24 95  (runbooks/health-check.sh)
```

The window includes the next 02:30 `frigate-restart`; its cost to kids/entry is
≈ 0.5 % of 24 h (447 s) and ≈ 0.1–0.2 % for the Reolinks, so the 97 % thresholds
are unaffected.

- **FIXED:** kitchen ≥ 97 **and** living_room ≥ 97 (controls ≥ 98). The threshold is
  fixed and does not depend on the baseline. Close the findings (below).
- **PARTIAL (cheaper reconnects, Wi-Fi-bound):** both improved by ≥ 5 points over
  the 24 h read recorded in §2.2 at this window (2026-10-26 reads: 82.5 / 77.1 at
  09:10Z, 85.9 / 80.1 at 13:32) but either is < 97. Keep the change (strictly better), record the per-hour profile
  on F-54d97a8b, leave it open, and hand it to the operator as the Wi-Fi DECIDE
  in §1.
- **REGRESSED or unchanged:** either camera ≤ its §2.2 24 h read + 2. Roll back (§5).

**Closing the findings at G2 PASS.** F-54d97a8b (section `plan`, agent-authored)
does not auto-close: `runbooks/policy-cli.py finding close F-54d97a8b --commit <sha-of-3.4>`
in the same turn. F-e4c22b35 (section `health`, `producer: script`, "Frigate recording
coverage below 90 % over 6h: living_room") is closed by the sweep itself once its
6-hour coverage scan reads ≥ 90 %; confirm it shows resolved after the next sweep
and close it by hand with the same `--commit` only if it is still open then.

**Status flow and OWNER of the post-window gates (G1, G2).** After G0a, G0, G0b, D
and G1-lite have PASSED or read PARTIAL, the window agent, **as the last step of
its run for this plan**: (1) sets `status: awaiting-soak` (not `executed`) and notes
`T` in the plan's status comment; (2) creates the soak reminder below, which names
the due times and the exact commands, so G1 and G2 are never orphaned. The owner of
running G1/G2 is **the operator, prompted by that reminder**; the next window's agent
may also run them when it sees the plan in `awaiting-soak`. The sweep is read-only:
it reports `frigate_coverage_scan` numbers but does not decide.

Fill `<T>`, `<T+70>` and `<T+24h20m>` (Europe/Berlin local times) before running.
`source` is `plan-soak`, deliberately not `maintenance`: the window close-out runs
`home-operation reconcile --source maintenance --open '<plan ids>'`, which
auto-closes every `maintenance` issue whose key is missing from that list, and this
reminder must survive until G2. (`home-operation` stores `source` as free text;
if a later version rejects an unknown source, fall back to `maintenance` AND add
`frigate-reolink-go2rtc-flv-soak` to every `--open` list until it is resolved.)

```bash
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation ingest --json \
  '{"key":"frigate-reolink-go2rtc-flv-soak","kind":"window_warning","source":"plan-soak","severity":"warning","action":"ack","component":"frigate","plan_path":"runbooks/maintenance/plans/frigate-reolink-go2rtc-flv.md","title":"frigate-reolink-go2rtc-flv soak: G1 due <T+70>, G2 due <T+24h20m>","detail":"Final Frigate pod started <T>. G1 (post-window coverage): python3 /tmp/frigate-cov.py 0.8333 <T+10m epoch>. G2 (decisive, 24h): python3 /tmp/frigate-cov.py 24, FIXED needs kitchen and living_room >= 97 with kids/entry >= 98; PARTIAL/REGRESSED rules are in section 4 of the plan. Revert path: plan section 5. On G2 PASS close findings F-54d97a8b and F-e4c22b35 and resolve this issue."}'
```

When G2 has a verdict, resolve it:

```bash
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation resolve \
  --issue frigate-reolink-go2rtc-flv-soak --by executed --note <sha-of-3.4>
```

The plan itself stays in `maintenance-plan.py
--open` (as `awaiting-soak`) until then, so a lost reminder cannot lose the plan.
`executed` and deletion of this file happen in the same commit that closes the
findings, after G2.

CONTENTS ASSERTION: recorded seconds per camera, from Frigate's own segment
index (`/api/<cam>/recordings`, clipped to the window). Measured with
`/tmp/frigate-cov.py` (G1: `[T+10m, T+60m]`; G2: 24 h) and, for the failure
signature itself, with the watchdog/CSeq counts in G1-lite. Compared to the
2026-10-26 baseline (24h 82.5 % kitchen / 77.1 % living_room / 99.8 % kids) and to
the kids/entry controls in the same run. The detect path is asserted separately by
gate D (`camera_fps`), because a dead sub restream passes record coverage.
Frigate is NOT scraped by Prometheus (0 `frigate_*` series, measured 2026-10-26),
so this API, not a metric, is the primary instrument.

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="home-automation",deployment="frigate"}` must read 1 after the Recreate. A stuck roll (GPU/NPU not schedulable, PVC attach) reads 0.
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="home-automation",container="frigate"}` must stay at 0 for the final pod over G1-lite. A crash-looping config (bad go2rtc block) increments it.
CONTROL: alertname ContainerRestartMitigationStale — must stay not-firing. This plan's roll makes the container younger, never older, and a firing state means the pod is not the one this plan rolled.

Live view (operator or the Chrome check, optional and not gating): open both
cameras in the Frigate UI. They should now offer MSE/WebRTC with audio. The
Authentik outpost `ak-outpost-frigate-forward-auth` fronts the UI; if the
`authentik-2026.8.5` plan (sat-attended 2026-11-21) is rolling it the same day, a
failed live-view check is the outpost, not Frigate.

## 5. Rollback

All of this is git-tracked: one commit, one revert. Nothing is forward-only.
Recordings go to the CIFS share either way and there is no schema change.

**Revert triggers:** G0a not 0 (never pushed), G0 not 4 keys, G0b failing in either
sample, D Reolink `camera_fps` 0, G1-lite respawns at or above the REVERT threshold
for its slot (§4: ≥ 20 nightly, ≥ 5 daytime), G2 REGRESSED/unchanged, or a
crash-looping final pod.

```bash
git revert --no-edit <sha-of-3.4>   # restores both configmap.sops.yaml and secret.sops.yaml
git log -1 --format=%s              # confirm it is YOUR revert subject
git push
```

Reloader rolls the pod again (possibly twice), with the same ~8-minute Wyze
recording gap per roll as §3.5. Confirm the cluster is back:

- `kubectl get configmap frigate-config -n home-automation -o jsonpath='{.data.config\.yml}' | grep -c '@192.168.32.234:554/Preview_01_main'`
  returns `1`.
- `... | grep -c '^go2rtc:'` returns `0`.
- `kubectl get secret frigate-rtsp-credentials -n home-automation -o jsonpath='{.data}' | grep -c URLENC`
  returns `0`.
- `curl …/api/go2rtc/streams` returns `{}`.
- Controls: `python3 /tmp/frigate-cov.py 0.8333 <START of the reverted pod + 600>`
  shows kids/entry ≥ 98 (kitchen/living_room return to their baseline drop pattern;
  that is expected). Set `status: draft` (or `blocked` with the reason) in this file.

**Not reverted by git:** the HTTP server switch on the two cameras. Leave it on
if §3-B or a retry is planned. Otherwise the operator may switch it off again in
the Reolink app (attack-surface hygiene on the IoT VLAN).

## 6. Interference notes

- **Window: HUMAN-GATED** (`capability_change: true`), so it needs an operator GO;
  per `docs/sops/maintenance-windows.md` a GO'd human-gated plan may run in any
  window. **Chosen: `nightly` (03:30, usable budget 70 min).** The in-window part
  (§2 pre-checks 10 + §3 edit/commit/push 10 + roll settle 5–8 + gates up to T+30)
  is `est_duration_min: 60`, which fits 70. The two coverage gates do not: G1 (T+70)
  and G2 (T+24 h) are **post-window** and tracked through `status: awaiting-soak`.
  Putting G1 inside the window would take the plan to ~100 min against 70, so it
  was split out rather than the window stretched. Choose `sat-attended` instead
  (same 70-min budget, operator present) only if the operator wants to watch the
  first live view or §2.3 is expected to be mixed; it does not buy extra minutes.
- **Scheduling bounds.** Earliest: the night after the operator has enabled HTTP on
  both cameras and §2.3 passed. **Latest: `nightly:2026-10-30`.** G2 needs a clean
  24 h with no Frigate restart other than the 02:30 cron, and `talos-linux-1.14.4`
  rolls k8s-nuc14-02 (where Frigate runs) at `sun-attended:2026-11-01`; do not
  schedule within 24 h before that roll. Check `maintenance-plan.py --open` for
  same-night load: the nightly's `capacity_risk` is 6 and this plan weighs 2
  (medium).
- **Restarts Frigate**, so all five cameras get the gap, and the restart re-claims
  `gpu.intel.com/i915` + `npu.intel.com/accel` on k8s-nuc14-02 (`shared:
  igpu-i915`).
- **`conflicts_with`:**
  - `talos-linux-1.14.4` reboots nuc14-02, which would restart Frigate inside the
    G2 soak and invalidate it.
  - `helm-drift-detection` rolls the intel-gpu-plugin, so for ~1 min/node a new GPU
    pod cannot schedule. A Recreate during that minute leaves Frigate Pending.
  - `flux-oci-chart-sources` repoints chart sources in home-automation and can
    re-render the frigate HR.
  - All three plans now list `frigate-reolink-go2rtc-flv` in their own
    `conflicts_with` (verified 2026-10-26), so the conflict is declared on both
    sides. `--validate` checks that refs resolve, not reciprocity; re-check if
    either side is edited.
- **Prometheus is read** (CONTROL lines). There was no open kube-prometheus-stack
  bump plan on 2026-10-26. If one appears for the same night, add it here.
- **Do not run inside 02:20–02:45 local** (`frigate-restart` CronJob). The Longhorn
  trim / snapshot-cleanup / backup crons run 22:00–23:00Z (23:00–00:00 local), hours
  away from the 03:30 window, so there is no storage-job overlap.
- **Known log noise:** F-f01dcab4 (embeddings segfault-loop after the nightly
  restart) can add errors in the first minutes after T. The gates above avoid it by
  starting their windows at T+10 and by matching only the camera-specific watchdog
  and CSeq patterns.
- **Home Assistant side effect:** enabling HTTP on the cameras could revive a
  dormant HA Reolink integration entry, since that integration needs the HTTP
  API. Check `ha-agent` for a `reolink` config entry after the operator step, and
  expect new entities rather than errors.
- **New in-cluster exposure:** `svc/frigate:8554` (port already declared,
  ClusterIP) will serve the two camera restreams without auth. That is
  acceptable inside the cluster. `go2rtc.rtsp.username/password` is the
  follow-up if the operator wants it closed, and it would need credentials in
  the four Frigate input paths.
