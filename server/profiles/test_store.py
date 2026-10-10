import copy
from datetime import datetime, timezone
import os
import tempfile
import unittest
import uuid

from server.profiles.store import ProfileStore, Conflict


def recipe():
    return {"schema": "staged-v1", "name": "Fixture aislada, no receta cervecera", "target_sg": 1.010,
            "stages": [{"name": "Fermentación", "kind": "fermentation", "temperature_c": 18,
                        "ramp_c_per_hour": 0.5, "min_hours": 0, "max_hours": 100, "exit": "manual"},
                       {"name": "Verificación", "kind": "verification", "temperature_c": 20,
                        "ramp_c_per_hour": 0.5, "min_hours": 0, "max_hours": 100, "exit": "stable"},
                       {"name": "Enfriado", "kind": "cooling", "temperature_c": 4,
                        "ramp_c_per_hour": 0.5, "min_hours": 0, "max_hours": 100, "exit": "manual"}]}


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "profiles.sqlite")
        self.now = 1791633600000
        self.store = ProfileStore(self.path, lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def cmd(self, action, **kwargs):
        return self.store.command(dict(action=action, request_id=str(uuid.uuid4()), **kwargs))

    def save(self, body=None):
        return self.cmd("save_recipe", recipe=body or recipe())

    def start(self, saved=None, **kwargs):
        saved = saved or self.save()
        values = dict(recipe_id=saved["recipe_id"], version=saved["version"], name="Banco aislado",
                      og=1.050, initial_temperature_c=22, volume_l=20, classification="bench", fermenter="fermentador-1")
        values.update(kwargs)
        return self.cmd("start_batch", **values)["batch_id"]

    def bc(self, bid, action, **kwargs):
        return self.cmd(action, batch_id=bid, revision=self.store.batch(bid)["revision"], **kwargs)

    def reading(self, bid, hours_ago=0, sg=1.010):
        return self.bc(bid, "add_reading", corrected_sg=sg, measured_at=datetime.fromtimestamp((self.now-hours_ago*3600000)/1000, timezone.utc).isoformat(),
                       instrument="Fixture", sample_temperature_c=20, corrected=True)

    def test_version_is_pinned_and_recipe_is_detached(self):
        body = recipe()
        saved = self.save(body)
        bid = self.start(saved)
        body["stages"][0]["temperature_c"] = 25
        self.cmd("save_recipe", recipe_id=saved["recipe_id"], expected_version=1, recipe=body)
        self.assertEqual(self.store.batch(bid)["recipe"]["stages"][0]["temperature_c"], 18)
        self.assertEqual(len(self.store.snapshot()["recipes"][0]["versions"]), 2)

    def test_ramp_begins_at_actual_temperature_and_pause_freezes(self):
        bid = self.start()
        self.now += 2*3600000
        self.assertEqual(self.store.evaluate(self.store.batch(bid))["calculated_c"], 21)
        self.bc(bid, "pause")
        self.now += 24*3600000
        self.assertEqual(self.store.evaluate(self.store.batch(bid))["calculated_c"], 21)
        self.bc(bid, "resume")
        self.now += 3600000
        self.assertEqual(self.store.evaluate(self.store.batch(bid))["calculated_c"], 20.5)

    def test_no_automatic_transition_or_finish_after_duration(self):
        bid = self.start()
        self.now += 200*3600000
        state = self.store.snapshot()["evaluation"]
        self.assertTrue(state["duration_warning"])
        self.assertEqual(self.store.batch(bid)["stage_index"], 0)
        self.assertEqual(self.store.batch(bid)["status"], "active")
        self.assertFalse(state["remote_commands_enabled"])

    def test_cooling_requires_stable_density_and_manual_check(self):
        bid = self.start()
        self.bc(bid, "advance", confirm=True, reason="Ensayo")
        with self.assertRaises(Conflict):
            self.bc(bid, "advance", confirm=True, reason="Sin datos")
        self.now += 49*3600000
        for age in (48, 24, 0):
            self.reading(bid, age)
        self.assertFalse(self.store.evaluate(self.store.batch(bid))["transition_ready"])
        self.bc(bid, "diacetyl", status="approved", notes="Resultado manual de fixture")
        self.assertTrue(self.store.evaluate(self.store.batch(bid))["transition_ready"])
        self.bc(bid, "advance", confirm=True, reason="Confirmación explícita")
        self.assertEqual(self.store.batch(bid)["stage_index"], 2)

    def test_new_reading_invalidates_approval(self):
        bid = self.start()
        self.bc(bid, "diacetyl", status="approved", notes="Comprobado")
        self.reading(bid)
        self.assertEqual(self.store.batch(bid)["diacetyl"]["status"], "pending")

    def test_stale_density_does_not_authorize_transition(self):
        body = recipe()
        body["stages"][0]["exit"] = "attenuation"
        body["stages"][0]["attenuation_pct"] = 70
        bid = self.start(self.save(body))
        self.reading(bid)
        self.assertTrue(self.store.evaluate(self.store.batch(bid))["transition_ready"])
        self.now += 25*3600000
        state = self.store.evaluate(self.store.batch(bid))
        self.assertFalse(state["transition_ready"])
        self.assertEqual(state["attenuation_pct"], 80)
        self.assertEqual(state["target_progress_pct"], 100)

    def test_optimistic_lock_and_idempotence(self):
        bid = self.start()
        request = dict(action="pause", batch_id=bid, revision=1, request_id="same-operation")
        first = self.store.command(request)
        self.assertEqual(self.store.command(request), first)
        self.assertEqual(self.store.batch(bid)["revision"], 2)
        with self.assertRaises(Conflict):
            self.store.command(dict(request, action="resume"))
        with self.assertRaises(Conflict):
            self.cmd("resume", batch_id=bid, revision=1)

    def test_one_active_batch_including_paused(self):
        saved = self.save()
        bid = self.start(saved)
        self.bc(bid, "pause")
        with self.assertRaises(Conflict):
            self.start(saved)
        self.bc(bid, "cancel", reason="Cerrar fixture")
        self.start(saved)

    def test_late_reading_keeps_measurement_time_and_void_history(self):
        bid = self.start()
        self.now += 10*3600000
        self.reading(bid, 5)
        reading = self.store.readings(bid)[0]
        self.assertEqual(reading["recorded_ms"]-reading["measured_ms"], 5*3600000)
        with self.assertRaises(Conflict):
            self.reading(bid, 5)
        self.bc(bid, "void_reading", reading_id=reading["id"], reason="Corrección de captura")
        self.reading(bid, 5, 1.011)
        self.assertEqual(len(self.store.readings(bid)), 2)
        self.assertEqual(self.store.evaluate(self.store.batch(bid))["latest_density"]["corrected_sg"], 1.011)

    def test_invalid_input_rolls_back_without_event(self):
        bid = self.start()
        before = self.store.export(bid)
        for value in (float("nan"), True, 1.100):
            with self.assertRaises((ValueError, TypeError)):
                self.reading(bid, sg=value)
        self.assertEqual(self.store.export(bid)["events"], before["events"])
        self.assertEqual(self.store.batch(bid)["revision"], 1)

    def test_restart_preserves_state_and_events(self):
        bid = self.start()
        self.bc(bid, "pause")
        expected = self.store.export(bid)
        self.store.close()
        self.store = ProfileStore(self.path, lambda: self.now)
        self.assertEqual(self.store.export(bid), expected)
        self.assertEqual(self.store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_archiving_keeps_batch_and_blocks_new_starts(self):
        saved = self.save()
        bid = self.start(saved)
        self.cmd("archive_recipe", recipe_id=saved["recipe_id"])
        self.assertEqual(self.store.batch(bid)["recipe_version"], 1)
        with self.assertRaises(ValueError):
            self.start(saved, fermenter="another")

    def test_clock_rollback_does_not_authorize(self):
        bid = self.start()
        self.reading(bid)
        self.now -= 3600000
        self.assertFalse(self.store.evaluate(self.store.batch(bid))["transition_ready"])

    def test_minimum_duration_and_manual_confirmation_are_required(self):
        body = recipe()
        body["stages"][0]["min_hours"] = 2
        bid = self.start(self.save(body))
        with self.assertRaises(Conflict):
            self.bc(bid, "advance", confirm=True, reason="Antes de tiempo")
        self.now += 2*3600000
        with self.assertRaises(ValueError):
            self.bc(bid, "advance", reason="Sin confirmación")
        self.bc(bid, "advance", confirm=True, reason="Ahora sí")


if __name__ == "__main__":
    unittest.main()
