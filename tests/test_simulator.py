import queue
import unittest

from simulator import SimulatedSensor


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.sensor = SimulatedSensor(queue.Queue(), queue.Queue())

    def test_manual_velocity_updates_status_and_metrics(self):
        status = self.sensor.configure(velocity_mm_s=3.5)
        self.assertEqual("manual", status["mode"])
        self.assertEqual(3.5, status["velocity_mm_s"])
        snap = self.sensor._metrics_snapshot(3.5)
        self.assertTrue(snap["simulated"])
        self.assertEqual(3.5, max(snap["velocity"]["rms"]))

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.sensor.configure(mode="invalid")
        with self.assertRaises(ValueError):
            self.sensor.configure(velocity_mm_s=-1)


if __name__ == "__main__":
    unittest.main()
