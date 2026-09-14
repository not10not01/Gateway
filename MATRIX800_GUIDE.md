# Matrix800 NPU Gateway — Setup, Usage & Tuning Guide

Last updated: 2026-09-08

## 1. Overview

The Matrix800 is a standalone AI gateway: a tri-axial vibration sensor streams
motion data over Modbus RTU, an on-device model turns each window of samples
into a 128-d "fingerprint," and a small CPU-side classifier head matches that
fingerprint against a few reference classes the user recorded earlier. All of
this — recording samples, training, and live classification — runs on the
gateway itself, entirely through a web dashboard. No cloud, no PC required
day-to-day.

Full architecture and Modbus protocol details are in the vendor's
`software_guide.md`; this document covers **access, day-to-day use, tuning,
and the current known NPU limitation**.

## 2. Hardware & Network Access

- Two Ethernet ports:
  - `end1` — direct link to a PC, static LAN `192.168.2.0/24`, no internet route. This is how we've been reaching the device (`192.168.2.127`).
  - `end0` — uplink port. Plug into a router with internet and run `dhclient end0` to get outbound access (does not affect `end1`).
- Sensor connects via USB-serial (FTDI FT4232H) → shows up as `/dev/ttyUSB0`..`/dev/ttyUSB3`.
- SSH: `ssh guest@192.168.2.127`
- Default credentials: `guest`/`guest`, `root`/`root` (source: Artila official `software_guide.md`). `root` cannot SSH in directly — log in as `guest`, then `su -`.
- **Recommend changing these default passwords before shipping to a customer.**

## 3. Running the Application

There is currently **no systemd service** — the app is started manually. As root, in the project folder:

    cd /home/guest/matrix800-iso20816-gateway.new
    MATRIX800_HTTP_PORT=8080 venv312/bin/python3 app.py

- `MATRIX800_HTTP_PORT` — app.py binds `0.0.0.0` on port 80 by default, which needs root. 8080 avoids that if not running as root.
- `venv312` is a Python 3.12 virtualenv set up specifically for this app (see §7 for why). Always launch with `venv312/bin/python3`, not the system `python3` (3.14), or NPU/CPU model loading will silently fall back to a broken state.
- To run in the background (so it survives your SSH session ending, and so you can keep using the terminal):

    nohup env MATRIX800_HTTP_PORT=8080 venv312/bin/python3 app.py > app.log 2>&1 &
    disown
    tail -f app.log     # watch startup / runtime logs

- Dashboard: `http://192.168.2.127:8080` (or whatever the device's `end0`/`end1` IP is).

**TODO before customer handoff:** wrap this in a systemd unit (`Restart=always`) so the dashboard survives reboots and crashes without someone SSHing in.

## 4. Using the Web Dashboard

The left nav has 7 pages:

| Page | Purpose |
| --- | --- |
| Live waveform | Real-time raw/FFT view per sensor port. Good first check that a sensor is actually streaming. |
| Metrics data | Slower per-sensor stats (RMS, kurtosis, etc.) |
| Edge AI demo | Vendor NPU demo page (image/object demos, separate from the vibration classifier) |
| Data recording | Record labeled motion samples — this is the training data |
| Train model | Build/rebuild the classifier head from recorded samples |
| Live inference | Real-time predicted class + confidence for each connected sensor |
| Settings | Device/app settings |

Bottom-left corner always shows `inference: <mode>` (`npu` / `cpu` / `stub`) and sensor count — check this first if predictions look wrong; if it says `stub`, the backbone model never loaded (see §7).

### Recording workflow (`Data recording`)

1. **Name** — the class label (e.g. `idle`, `shaking`, `motor_running`). Reuse a name to add more samples to that class.
2. **Sensor port** — pick the connected sensor.
3. **Mode** — `Append` (add to existing recording for this label) or `Overwrite` (replace it).
4. **Duration** (seconds) or **Samples** — how long to record.
5. **Start recording** — physically perform the motion you're labeling while it records.

Existing recordings list shows sample count, duration, size, and last-modified — useful for spotting a label with too little data.

### Training (`Train model`)

- Lists every recorded label with an "eligible" flag (enough clean data to use).
- Select the labels you want in the model, click **Train model**.
- This is fast (seconds) — it's not deep-learning training, it's: run each recorded window through the fixed backbone model to get its 128-d fingerprint, then average the fingerprints per label. The result is written to `classifier_head.json` and hot-swapped into the live inference worker — no restart needed.
- **Current labels** at the top shows what the live classifier is actually using right now.

### Live inference

- Pick a sensor port, watch the predicted class name, confidence %, and a 7-sample majority-vote history update in real time.
- A prediction only latches after a majority of the last 7 windows agree — expect a ~1-2s lag when you change motion.

## 5. Basic Tuning Process

This is a nearest-fingerprint classifier, not a trained neural net — "tuning" mostly means **curating what you record**, not adjusting hyperparameters.

1. **Always record a baseline "idle/steady" class first.** Without one, any noise gets forced into whatever labels exist. Label it something explicit like `steady_state`.
2. **Record each motion class in multiple short takes (5-10s), Append mode, not one long take.** Multiple takes average out any one-off noise (a stray bump, a person's hand nearby) better than a single long recording.
3. **Keep motions distinct and consistent.** The classifier is cosine-similarity based — two classes that produce similar vibration signatures will get confused. If two labels are frequently swapped in Live inference, either merge them or make the physical motions more distinct.
4. **Re-record instead of trying to "average out" bad data.** If a take was contaminated (sensor bumped, wrong motion performed), delete it and re-record rather than appending more good data on top and hoping it dilutes the bad — the fingerprint average is sensitive to outlier windows.
5. **Re-train after every change to recordings.** Training is cheap (seconds) — there's no reason to batch up changes. Add a sample, hit Train model, check Live inference immediately.
6. **Use Live inference as your feedback loop.** Confidence sitting near-even across classes (not clearly near 100%) means the classes are too similar or a recording is noisy — go back to step 3/4, don't try to fix it by editing the model.
7. **Serial latency matters more than people expect.** At 7812 Hz sample rate, default 16ms USB latency will cause missed/garbled reads. Set this once per boot (does not persist across reboot, consider adding to a startup script):

    echo 1 > /sys/bus/usb-serial/devices/ttyUSB*/latency_timer

## 6. NPU Acceleration — Current Status (Known Issue)

**Short version: inference/training works today, but on CPU, not the NPU.** Real-time performance is fine for this model at this sample rate, but it's running without hardware acceleration.

### What we found

The board supports two NPU driver paths (see vendor `software_guide.md`):

| | NXP (Ethos-U) | Mesa (teflon) |
| --- | --- | --- |
| Status on this unit | Kernel driver (`ethosu`) loads fine, delegate `.so` present, **but its runtime dependency `libtensorflow-lite.so.2.18.0` is missing device-wide and not in the apt repo** (only wrong-version `2.14.1` exists) | **Kernel has no DRM/accel driver compiled in at all** (`/lib/modules/.../kernel/drivers/accel/` doesn't exist, no `rocket` module) — confirmed via `dmesg`, `lsmod`, `find`. Rebooting did not change this. Structurally can't work on this kernel build regardless of config. |
| Verdict | Blocked on a missing vendor file | Not supported by this kernel build |

Both hardware-acceleration paths are currently dead ends **without vendor input**. This is not a configuration or packaging issue we can resolve from the device — `libtensorflow-lite.so.2.18.0` appears to be something that should ship with the device image but is absent on this unit.

### What we did instead: CPU fallback

`inference.py` was patched so the delegate is optional (`MATRIX800_DELEGATE=""` skips it and loads a plain, non-delegated `tflite_runtime.Interpreter`). With the non-vela model (`models/vibration_backbone_int8.tflite` — the vela-compiled one is NPU-only and won't run without the delegate), the full pipeline works end-to-end on CPU:

    nohup env MATRIX800_HTTP_PORT=8080 \
      MATRIX800_DELEGATE="" \
      MATRIX800_NPU_MODEL=models/vibration_backbone_int8.tflite \
      venv312/bin/python3 app.py > app.log 2>&1 &
    disown

Verified working end-to-end via the dashboard: recorded a sample, trained a head from 4 labels, and Live inference correctly classified in real time (`inference: cpu` shown bottom-left).

Vendor's own benchmark table (`software_guide.md`) shows NPU is ~1.9x–17x faster than CPU depending on the model — so this is a real performance gap, just not a functional blocker for this demo's sample rate.

### To restore NPU acceleration later

Once `libtensorflow-lite.so.2.18.0` (aarch64) is obtained from Artila/NXP and placed at a location on the linker path (e.g. `/usr/local/lib/`), switch back with no code changes needed:

    nohup env MATRIX800_HTTP_PORT=8080 venv312/bin/python3 app.py > app.log 2>&1 &

(i.e. drop the two env var overrides — the code defaults back to the vela model + `libethosu_delegate.so`.)

### Escalation needed

Contact Artila support (or NXP, since this is their Ethos-U delegate) and ask specifically for:
- `libtensorflow-lite.so.2.18.0` (aarch64) matching the `libethosu_delegate.so` shipped on this device, **or**
- Confirmation of which BSP/eIQ SDK release includes it, so it can be extracted from there.

Reference their own `software_guide.md` NXP-path section — it documents the delegate but not this runtime dependency, which suggests it's meant to be preinstalled and is simply missing from this unit's image.

## 7. Appendix: Why a Python 3.12 venv

The NXP delegate's pip wheel (`tflite_runtime-2.18.0-cp312-cp312-linux_aarch64.whl`, at `/opt/npu/wheels/`) is built for CPython 3.12 specifically. The device ships Python 3.14 with no 3.12 available via apt, so Python 3.12.8 was compiled from source (`./configure --prefix=/usr/local --enable-shared && make -j2 && make altinstall`) and a venv (`venv312`) created from it, with all of `requirements.txt` plus `tflite_runtime`/`ai-edge-litert` installed into it.

One app-level fix was needed alongside this: `app.py` unconditionally inserted a bundled `./.packages` directory (containing a Python-3.14-only numpy build) at the front of `sys.path`, which shadowed the venv's own correctly-installed numpy. Fixed by making that insert conditional on `sys.prefix == sys.base_prefix` (i.e. only applies when *not* running inside a venv), so the original system-Python stub-mode launch path is untouched.
