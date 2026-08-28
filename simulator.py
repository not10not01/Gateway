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
        self._started_at = time.monotonic()
        self._sample_index = 0

    def configure(self, mode=None, velocity_mm_s=None):
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
            return self.status()

    def status(self):
        with self._lock:
            return {"enabled": True, "port": self.port,
                    "mode": self._mode,
                    "velocity_mm_s": self._current_velocity_locked()}

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

    def run(self):
        chunk_size = 217
        next_metrics = 0.0
        while True:
            with self._lock:
                velocity = self._current_velocity_locked()
            # A stable 30 Hz three-axis acceleration waveform for the live page.
            idx = np.arange(self._sample_index,
                            self._sample_index + chunk_size, dtype=np.float32)
            phase = 2.0 * math.pi * 30.0 * idx / self.sample_rate
            amplitude_g = 0.02 + velocity * 0.004
            chunk = np.column_stack((
                amplitude_g * np.sin(phase),
                amplitude_g * 0.8 * np.sin(phase + 0.7),
                amplitude_g * 0.6 * np.sin(phase + 1.4),
            )).astype(np.float32)
            self._sample_index += chunk_size
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
