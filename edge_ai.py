"""Tiny FFT-feature model for a zero-dependency Edge AI demonstration."""

import json
import os
import threading
import time

import numpy as np


DEFAULT_MODEL_PATH = os.path.join("models", "tiny_fault_model.json")


class TinyFaultModel:
    def __init__(self, path=DEFAULT_MODEL_PATH, sample_rate=7812, window_size=3906):
        with open(path, "r", encoding="utf-8") as stream:
            spec = json.load(stream)
        self.name = spec["name"]
        self.version = spec["version"]
        self.labels = spec["labels"]
        self.prototypes = np.asarray(spec["prototypes"], dtype=np.float32)
        self.scales = np.asarray(spec["feature_scales"], dtype=np.float32)
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.feature_names = spec["features"]

    def extract(self, samples):
        axis = np.asarray(samples[:, 1], dtype=np.float32)
        axis = axis - np.mean(axis)
        rms = float(np.sqrt(np.mean(axis * axis)))
        crest = float(np.max(np.abs(axis)) / max(rms, 1e-7))
        spectrum = np.abs(np.fft.rfft(axis * np.hanning(len(axis))))
        freqs = np.fft.rfftfreq(len(axis), 1.0 / self.sample_rate)

        def band(center, width=4.0):
            mask = (freqs >= center - width) & (freqs <= center + width)
            return float(np.sum(spectrum[mask]))

        p30, p60, p90, p300 = (band(30), band(60), band(90), band(300, 20))
        selected = max(p30 + p60 + p90 + p300, 1e-7)
        high = float(np.sum(spectrum[(freqs >= 180) & (freqs <= 800)]))
        total = max(float(np.sum(spectrum[1:])), 1e-7)
        return np.asarray([
            rms, crest, p30 / selected, p60 / selected,
            p90 / selected, p300 / selected, high / total,
        ], dtype=np.float32)

    def predict(self, samples):
        started = time.perf_counter()
        features = self.extract(samples)
        distance = np.sqrt(np.sum(
            ((self.prototypes - features) / self.scales) ** 2, axis=1))
        logits = -2.2 * distance
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= np.sum(probabilities)
        winner = int(np.argmax(probabilities))
        return {
            "label": self.labels[winner],
            "confidence": round(float(probabilities[winner]), 4),
            "probabilities": {
                label: round(float(probabilities[i]), 4)
                for i, label in enumerate(self.labels)
            },
            "features": {
                name: round(float(features[i]), 5)
                for i, name in enumerate(self.feature_names)
            },
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "backend": "NumPy / ARM Cortex-A55",
            "model": self.name,
            "model_version": self.version,
            "timestamp": time.time(),
        }


class EdgeAIEngine:
    def __init__(self, ports, model, window_size=3906):
        self.model = model
        self.window_size = window_size
        self._buffers = {port: np.empty((0, 3), dtype=np.float32) for port in ports}
        self._latest = {port: None for port in ports}
        self._last_run = {port: 0.0 for port in ports}
        self._lock = threading.Lock()

    def append(self, port, chunk):
        if port not in self._buffers:
            return
        with self._lock:
            merged = np.concatenate((self._buffers[port], chunk), axis=0)
            self._buffers[port] = merged[-self.window_size:]
            now = time.monotonic()
            if len(self._buffers[port]) < self.window_size or now - self._last_run[port] < 0.5:
                return
            window = self._buffers[port].copy()
            self._last_run[port] = now
        result = self.model.predict(window)
        with self._lock:
            self._latest[port] = result

    def snapshot(self):
        with self._lock:
            return {"ports": dict(self._latest), "model": self.model.name,
                    "backend": "NumPy / ARM Cortex-A55"}
