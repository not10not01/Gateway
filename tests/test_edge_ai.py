import os
import unittest

import numpy as np

from edge_ai import TinyFaultModel
from simulator import SimulatedSensor


class EdgeAITests(unittest.TestCase):
    def setUp(self):
        model_path = os.path.join(os.path.dirname(__file__), "..", "models",
                                  "tiny_fault_model.json")
        self.model = TinyFaultModel(model_path)
        self.sensor = SimulatedSensor(None, None)

    def make_window(self, fault):
        self.sensor._sample_index = 0
        chunks = [self.sensor._make_chunk(3.0, fault, 217) for _ in range(19)]
        return np.concatenate(chunks, axis=0)[-3906:]

    def test_all_synthetic_faults_are_classified(self):
        expected = {
            "normal": "Normal", "imbalance": "Imbalance",
            "misalignment": "Misalignment", "looseness": "Looseness",
            "bearing": "Bearing impact",
        }
        for fault, label in expected.items():
            with self.subTest(fault=fault):
                self.assertEqual(label, self.model.predict(self.make_window(fault))["label"])


if __name__ == "__main__":
    unittest.main()
