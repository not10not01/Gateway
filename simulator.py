"""Synthetic vibration sensor used before Modbus hardware is available."""

import math
import threading
import time

import numpy as np


SIMULATED_PORT = "/dev/sim0"


class SimulatedSensor(threading.Thread):
    def __init__(self, metrics_queue, raw_queue, port=SIMULATED_PORT,
                 sample_rate=7812, initial_velocity=0.8):
        super().__init__(daemon=True, name="simulated-sensor")
        self.metrics_queue = metrics_queue
        self.raw_queue = raw_queue
        self.port = port
        self.sample_rate = sample_rate
        self._lock = threading.RLock()
        self._mode = "auto"
        self._velocity = float(initial_velocity)
        self._fault = "normal"
        self._started_at = time.monotonic()
        self._sample_index = 0

    def configure(self, mode=None, velocity_mm_s=None, fault=None):
        with self._lock:
            if mode is not None:
                if mode not in ("auto", "manual"):
                    raise ValueError("mode must be auto or manual")
                self._mode = mode
            if velocity_mm_s is not None:
                value = float(velocity_mm_s)
                if not 0 <= value <= 100:
                    raise ValueError("velocity_mm_s must be between 0 and 100")
                self._velocity = value
                self._mode = "manual"
            if fault is not None:
                fault = str(fault).strip().lower()
                allowed = ("normal", "imbalance", "misalignment", "looseness", "bearing")
                if fault not in allowed:
                    raise ValueError("fault must be one of: " + ", ".join(allowed))
                self._fault = fault
                self._mode = "manual"
                self._velocity = {
                    "normal": 0.8, "imbalance": 3.5, "misalignment": 3.2,
                    "looseness": 4.0, "bearing": 5.2,
                }[fault]
            return self.status()

    def status(self):
        with self._lock:
            return {"enabled": True, "port": self.port,
                    "mode": self._mode,
                    "velocity_mm_s": self._current_velocity_locked(),
                    "fault": self._fault}

    def _current_velocity_locked(self):
        if self._mode == "manual":
            return self._velocity
        # G2-rigid examples: A, B, C and D, ten seconds per zone.
        values = (0.8, 2.0, 3.5, 5.5)
        step = int((time.monotonic() - self._started_at) / 10.0)
        return values[step % len(values)]

    def _metrics_snapshot(self, velocity):
        axes = [round(velocity * 0.82, 3), round(velocity, 3),
                round(velocity * 0.68, 3)]
        return {
            "ts": time.time(), "temperature": 28.5,
            "gravity": {
                "rms": [0.08, 0.10, 0.07],
                "peak": [0.16, 0.20, 0.14],
                "crest": [2.0, 2.0, 2.0],
                "skewness": [0.0, 0.0, 0.0],
                "kurtosis": [3.0, 3.0, 3.0],
                "primary_freq": 30.0,
            },
            "velocity": {
                "rms": axes,
                "peak": [round(v * 2.0, 3) for v in axes],
                "crest": [2.0, 2.0, 2.0],
                "primary_freq": 30.0,
            },
            "simulated": True,
        }

    def _make_chunk(self, velocity, fault, chunk_size):
        idx = np.arange(self._sample_index,
                        self._sample_index + chunk_size, dtype=np.float32)
        t = idx / self.sample_rate
        p1 = 2.0 * math.pi * 30.0 * t
        base = 0.022 * np.sin(p1)
        if fault == "imbalance":
            signal = 0.10 * np.sin(p1)
        elif fault == "misalignment":
            signal = 0.055 * np.sin(p1) + 0.040 * np.sin(2 * p1 + 0.3)
        elif fault == "looseness":
            signal = (0.050 * np.sin(p1) + 0.032 * np.sin(2 * p1) +
                      0.025 * np.sin(3 * p1 + 0.4))
            signal *= 1.0 + 0.45 * np.sin(2.0 * math.pi * 3.0 * t)
        elif fault == "bearing":
            carrier = np.sin(2.0 * math.pi * 300.0 * t)
            impacts = np.maximum(0.0, np.sin(2.0 * math.pi * 12.0 * t)) ** 10
            signal = 0.018 * np.sin(p1) + 0.12 * impacts * carrier
        else:
            signal = base
        chunk = np.column_stack((
            signal, 0.82 * np.roll(signal, 7), 0.66 * np.roll(signal, 13)
        )).astype(np.float32)
        self._sample_index += chunk_size
        return chunk

    def run(self):
        chunk_size = 217
        next_metrics = 0.0
        while True:
            with self._lock:
                velocity = self._current_velocity_locked()
                fault = self._fault
            chunk = self._make_chunk(velocity, fault, chunk_size)
            try:
                self.raw_queue.put_nowait((self.port, chunk))
            except Exception:
                pass
            now = time.monotonic()
            if now >= next_metrics:
                try:
                    self.metrics_queue.put_nowait(
                        (self.port, self._metrics_snapshot(velocity)))
                except Exception:
                    pass
                next_metrics = now + 0.5
            time.sleep(chunk_size / self.sample_rate)
