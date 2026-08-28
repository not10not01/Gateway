"""ISO 20816-3:2022 severity evaluation for gateway velocity metrics.

This module deliberately does not claim to diagnose a fault or stop a machine.
It maps a configured machine profile and broad-band velocity RMS measurement to
the guideline zones described in ISO 20816-3 Annex A.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time


STANDARD = "ISO 20816-3:2022"
ZONE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}

# A/B, B/C and C/D boundaries in mm/s RMS.
LIMITS = {
    "G1-R": (2.3, 4.5, 7.1),
    "G1-F": (3.5, 7.1, 11.0),
    "G2-R": (1.4, 2.8, 4.5),
    "G2-F": (2.3, 4.5, 7.1),
}

ZONE_ACTIONS = {
    "A": "Newly commissioned / good condition",
    "B": "Acceptable for unrestricted long-term operation",
    "C": "Unsatisfactory for long-term operation; schedule inspection",
    "D": "Risk of damage; assess immediately under the site shutdown policy",
}

DEFAULT_PROFILE = {
    "enabled": False,
    "rpm": None,
    "rated_power_kw": None,
    "shaft_height_mm": None,
    "support": "rigid",
    "group": "auto",
    "hold_seconds": 10.0,
    "hysteresis_mm_s": 0.2,
}


def _optional_float(value, field):
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(out) or out <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return out


def normalise_profile(profile):
    """Validate user input and return a complete JSON-serialisable profile."""
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    out = dict(DEFAULT_PROFILE)
    out.update(profile)
    out["enabled"] = bool(out["enabled"])
    out["rpm"] = _optional_float(out.get("rpm"), "rpm")
    out["rated_power_kw"] = _optional_float(
        out.get("rated_power_kw"), "rated_power_kw")
    out["shaft_height_mm"] = _optional_float(
        out.get("shaft_height_mm"), "shaft_height_mm")

    support = str(out.get("support", "")).strip().lower()
    if support not in ("rigid", "flexible"):
        raise ValueError("support must be rigid or flexible")
    out["support"] = support

    group = str(out.get("group", "auto")).strip().lower()
    if group not in ("auto", "1", "2"):
        raise ValueError("group must be auto, 1 or 2")
    out["group"] = group

    try:
        hold_raw = out.get("hold_seconds", 10.0)
        hysteresis_raw = out.get("hysteresis_mm_s", 0.2)
        hold = float(10.0 if hold_raw in (None, "") else hold_raw)
        hysteresis = float(0.2 if hysteresis_raw in (None, "") else hysteresis_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("hold_seconds and hysteresis_mm_s must be numbers") from exc
    if not math.isfinite(hold) or not 0 <= hold <= 3600:
        raise ValueError("hold_seconds must be between 0 and 3600")
    if not math.isfinite(hysteresis) or not 0 <= hysteresis <= 10:
        raise ValueError("hysteresis_mm_s must be between 0 and 10")
    out["hold_seconds"] = hold
    out["hysteresis_mm_s"] = hysteresis
    return out


def resolve_group(profile):
    requested = profile["group"]
    if requested in ("1", "2"):
        return int(requested), "manual"

    power = profile.get("rated_power_kw")
    height = profile.get("shaft_height_mm")
    if power is not None:
        if power > 300:
            return 1, "rated_power_kw"
        if power > 15:
            return 2, "rated_power_kw"
        return None, "rated power is not above 15 kW"
    if height is not None:
        if height >= 315:
            return 1, "shaft_height_mm"
        if height >= 160:
            return 2, "shaft_height_mm"
        return None, "shaft height is below 160 mm"
    return None, "rated power or shaft height is required"


def resolve_frequency_band(rpm):
    if rpm is None:
        return None, "rpm is required"
    if rpm > 600:
        return [10.0, 1000.0], None
    if rpm >= 120:
        return [2.0, 1000.0], None
    return None, "ISO 20816-3 is not selected for speeds below 120 rpm"


def zone_for_value(value, boundaries):
    ab, bc, cd = boundaries
    if value < ab:
        return "A"
    if value < bc:
        return "B"
    if value < cd:
        return "C"
    return "D"


def _clean_axes(values):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        return None
    axes = []
    for value in values:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        axes.append(value)
    return axes


def evaluate(values, profile):
    """Return an instantaneous ISO result without alarm state or time delay."""
    profile = normalise_profile(profile)
    result = {
        "standard": STANDARD,
        "enabled": profile["enabled"],
        "applicable": False,
        "source": "sensor_velocity_rms",
        "zone": None,
        "raw_zone": None,
        "action": None,
    }
    if not profile["enabled"]:
        result["reason"] = "ISO evaluation is disabled for this sensor"
        return result

    group, group_source = resolve_group(profile)
    band, band_error = resolve_frequency_band(profile.get("rpm"))
    if group is None:
        result["reason"] = group_source
        return result
    if band_error:
        result["reason"] = band_error
        return result

    axes = _clean_axes(values)
    if axes is None:
        result["reason"] = "three valid non-negative velocity RMS axes are required"
        return result

    support_code = "R" if profile["support"] == "rigid" else "F"
    profile_code = f"G{group}-{support_code}"
    boundaries = LIMITS[profile_code]
    max_value = max(axes)
    max_axis = "XYZ"[axes.index(max_value)]
    zone = zone_for_value(max_value, boundaries)
    result.update({
        "applicable": True,
        "reason": None,
        "group": group,
        "group_source": group_source,
        "support": profile["support"],
        "profile_code": profile_code,
        "frequency_band_hz": band,
        "velocity_rms_axes_mm_s": axes,
        "velocity_rms_mm_s": max_value,
        "max_axis": max_axis,
        "boundaries_mm_s": {
            "ab": boundaries[0], "bc": boundaries[1], "cd": boundaries[2]},
        "zone": zone,
        "raw_zone": zone,
        "action": ZONE_ACTIONS[zone],
        "alarm": zone in ("C", "D"),
    })
    return result


class ProfileStore:
    """Thread-safe, atomic JSON profile persistence keyed by serial port."""

    def __init__(self, path):
        self._path = path
        self._lock = threading.Lock()
        self._profiles = self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            if isinstance(data, dict):
                return {str(port): normalise_profile(profile)
                        for port, profile in data.items()}
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"[iso20816] failed to load {self._path}: {exc}; using defaults")
        return {}

    def _save_locked(self):
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(self._profiles, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)

    def get(self, port):
        with self._lock:
            return dict(self._profiles.get(port, DEFAULT_PROFILE))

    def set(self, port, profile):
        clean = normalise_profile(profile)
        with self._lock:
            self._profiles[port] = clean
            self._save_locked()
        return dict(clean)

    def as_dict(self, ports=None):
        with self._lock:
            keys = ports if ports is not None else self._profiles.keys()
            return {port: dict(self._profiles.get(port, DEFAULT_PROFILE))
                    for port in keys}


class StableEvaluator:
    """Add confirmation time and recovery hysteresis to instantaneous zones."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._states = {}

    def reset(self, port):
        with self._lock:
            self._states.pop(port, None)

    def update(self, port, values, profile, timestamp=None):
        instant = evaluate(values, profile)
        if not instant["applicable"]:
            return instant

        now = self._clock()
        with self._lock:
            state = self._states.get(port)
            if state is None:
                state = {
                    "zone": instant["raw_zone"],
                    "since": now,
                    "candidate": None,
                    "candidate_since": None,
                }
                self._states[port] = state

            raw_zone = instant["raw_zone"]
            stable_zone = state["zone"]
            hysteresis = profile.get("hysteresis_mm_s", 0.2)

            # To recover to a better zone, the value must clear the active
            # zone's lower boundary by the configured margin.
            if ZONE_ORDER[raw_zone] < ZONE_ORDER[stable_zone]:
                boundaries = LIMITS[instant["profile_code"]]
                lower_boundary = boundaries[ZONE_ORDER[stable_zone] - 1]
                if instant["velocity_rms_mm_s"] > max(0.0, lower_boundary - hysteresis):
                    raw_zone = stable_zone

            if raw_zone == stable_zone:
                state["candidate"] = None
                state["candidate_since"] = None
            else:
                if state["candidate"] != raw_zone:
                    state["candidate"] = raw_zone
                    state["candidate_since"] = now
                hold = profile.get("hold_seconds", 10.0)
                if now - state["candidate_since"] >= hold:
                    state["zone"] = raw_zone
                    state["since"] = now
                    state["candidate"] = None
                    state["candidate_since"] = None

            stable_zone = state["zone"]
            instant.update({
                "zone": stable_zone,
                "action": ZONE_ACTIONS[stable_zone],
                "alarm": stable_zone in ("C", "D"),
                "pending_zone": state["candidate"],
                "pending_seconds": (None if state["candidate_since"] is None
                                    else max(0.0, now - state["candidate_since"])),
                "state_age_seconds": max(0.0, now - state["since"]),
                "measurement_ts": timestamp,
            })
        return instant
