import json
import os
import tempfile
import unittest

from iso20816 import (LIMITS, ProfileStore, StableEvaluator, evaluate,
                      normalise_profile, resolve_frequency_band)


def profile(**overrides):
    out = {
        "enabled": True,
        "rpm": 1800,
        "rated_power_kw": 75,
        "shaft_height_mm": None,
        "support": "rigid",
        "group": "auto",
        "hold_seconds": 10,
        "hysteresis_mm_s": 0.2,
    }
    out.update(overrides)
    return normalise_profile(out)


class Iso20816Tests(unittest.TestCase):
    def test_pdf_boundaries_are_preserved(self):
        self.assertEqual(LIMITS["G1-R"], (2.3, 4.5, 7.1))
        self.assertEqual(LIMITS["G1-F"], (3.5, 7.1, 11.0))
        self.assertEqual(LIMITS["G2-R"], (1.4, 2.8, 4.5))
        self.assertEqual(LIMITS["G2-F"], (2.3, 4.5, 7.1))

    def test_group_2_rigid_example_is_zone_c(self):
        result = evaluate([3.2, 1.0, 0.5], profile())
        self.assertTrue(result["applicable"])
        self.assertEqual(result["profile_code"], "G2-R")
        self.assertEqual(result["max_axis"], "X")
        self.assertEqual(result["zone"], "C")

    def test_pdf_compressor_values_change_with_support(self):
        rigid_s1 = evaluate([3.77, 1, 1], profile(support="rigid"))
        rigid_s2 = evaluate([5.62, 1, 1], profile(support="rigid"))
        flexible_s1 = evaluate([3.77, 1, 1], profile(support="flexible"))
        flexible_s2 = evaluate([5.62, 1, 1], profile(support="flexible"))
        self.assertEqual(
            [rigid_s1["zone"], rigid_s2["zone"],
             flexible_s1["zone"], flexible_s2["zone"]],
            ["C", "D", "B", "C"],
        )

    def test_frequency_band_selection_and_low_speed_scope(self):
        self.assertEqual(resolve_frequency_band(601), ([10.0, 1000.0], None))
        self.assertEqual(resolve_frequency_band(600), ([2.0, 1000.0], None))
        self.assertIsNotNone(resolve_frequency_band(119)[1])

    def test_stable_evaluator_applies_hold_and_recovery_hysteresis(self):
        now = [0.0]
        monitor = StableEvaluator(clock=lambda: now[0])
        config = profile()

        self.assertEqual(monitor.update("p", [2.0, 1, 1], config)["zone"], "B")
        now[0] = 1
        pending = monitor.update("p", [3.0, 1, 1], config)
        self.assertEqual(pending["zone"], "B")
        self.assertEqual(pending["pending_zone"], "C")
        now[0] = 11
        self.assertEqual(monitor.update("p", [3.0, 1, 1], config)["zone"], "C")

        # 2.7 is below B/C but not below the 2.8 - 0.2 recovery threshold.
        now[0] = 12
        self.assertEqual(monitor.update("p", [2.7, 1, 1], config)["zone"], "C")
        now[0] = 13
        self.assertEqual(monitor.update("p", [2.5, 1, 1], config)["zone"], "C")
        now[0] = 23
        self.assertEqual(monitor.update("p", [2.5, 1, 1], config)["zone"], "B")

    def test_profile_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "profiles.json")
            store = ProfileStore(path)
            saved = store.set("/dev/ttyUSB0", profile())
            with open(path, "r", encoding="utf-8") as stream:
                on_disk = json.load(stream)
            self.assertEqual(on_disk["/dev/ttyUSB0"], saved)
            self.assertEqual(ProfileStore(path).get("/dev/ttyUSB0"), saved)

    def test_disabled_and_invalid_measurements_fail_closed(self):
        disabled = evaluate([3.2, 1, 1], profile(enabled=False))
        invalid = evaluate([3.2, None, 1], profile())
        self.assertFalse(disabled["applicable"])
        self.assertFalse(invalid["applicable"])


if __name__ == "__main__":
    unittest.main()
