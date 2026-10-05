from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest

from server.fermentation import GravityReading, RecipeStore, apparent_attenuation, gravity_is_stable, target_progress


class FermentationTest(unittest.TestCase):
    def test_attenuation_and_target_progress_are_different(self):
        self.assertAlmostEqual(apparent_attenuation(1.050, 1.020), 60)
        self.assertAlmostEqual(target_progress(1.050, 1.020, 1.010), 75)

    def test_invalid_gravity(self):
        for initial, current in [(1, 1), (1.05, 1.06), (1.05, float("nan")), (True, 1.01)]:
            with self.assertRaises(ValueError):
                apparent_attenuation(initial, current)

    def test_stable_requires_time_coverage_and_recent_samples(self):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        samples = [GravityReading(now - timedelta(hours=h), 1.010) for h in (48, 24, 0)]
        self.assertTrue(gravity_is_stable(samples, now))
        self.assertFalse(gravity_is_stable(samples[1:], now))
        self.assertFalse(gravity_is_stable(samples, now + timedelta(hours=49)))
        samples[-1] = GravityReading(now, 1.006)
        self.assertFalse(gravity_is_stable(samples, now))

    def test_future_or_duplicate_samples(self):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            gravity_is_stable([GravityReading(now + timedelta(seconds=1), 1.01)], now)
        sample = GravityReading(now - timedelta(hours=48), 1.01)
        self.assertFalse(gravity_is_stable([sample, sample, GravityReading(now, 1.01)], now))

    def test_recipes_persist_and_previous_versions_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "recipes.sqlite")
            recipe = {"name": "Perfil de prueba", "stages": [{"day": 0, "temperature_c": 18}]}
            store = RecipeStore(path)
            self.assertEqual(store.save("prueba", recipe), 1)
            recipe["stages"][0]["temperature_c"] = 20
            self.assertEqual(store.save("prueba", recipe), 2)
            store.close()
            store = RecipeStore(path)
            self.assertEqual(store.load("prueba", 1)["stages"][0]["temperature_c"], 18)
            self.assertEqual(store.load("prueba")["stages"][0]["temperature_c"], 20)
            self.assertEqual(store.list_versions(), [("prueba", 1), ("prueba", 2)])
            store.close()

    def test_invalid_recipe_does_not_create_version(self):
        store = RecipeStore(":memory:")
        for stages in ([], [{"day": 1, "temperature_c": 18}], [{"day": 0, "temperature_c": 30}], [{"day": 0, "temperature_c": 18}, {"day": 0, "temperature_c": 20}]):
            with self.assertRaises(ValueError):
                store.save("prueba", {"name": "Prueba", "stages": stages})
        self.assertEqual(store.list_versions(), [])
        store.close()


if __name__ == "__main__":
    unittest.main()
