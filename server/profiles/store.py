"""Estado transaccional, recetas inmutables e historial de decisiones manuales."""
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone

from server.fermentation import RecipeStore, GravityReading, checked_gravity, apparent_attenuation, target_progress, gravity_is_stable


class Conflict(ValueError):
    pass


def text(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + " inválido")
    return value.strip()


def number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(label + " fuera de rango")
    return value


def validate_staged_recipe(recipe):
    result = json.loads(json.dumps(recipe, allow_nan=False))
    result["name"] = text(result.get("name"), "Nombre")
    for key in ("yeast", "style", "notes"):
        if not isinstance(result.get(key, ""), str) or len(result.get(key, "")) > 2000:
            raise ValueError("Texto inválido: " + key)
    stages = result.get("stages")
    if not isinstance(stages, list) or not 1 <= len(stages) <= 20:
        raise ValueError("Se necesitan entre una y veinte etapas")
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("Etapa inválida")
        text(stage.get("name"), "Nombre de etapa")
        if stage.get("kind") not in ("fermentation", "rest", "verification", "cooling"):
            raise ValueError("Tipo de etapa inválido")
        number(stage.get("temperature_c"), "Temperatura", 0.1, 29.9)
        number(stage.get("ramp_c_per_hour"), "Rampa", 0.01, 5)
        minimum = number(stage.get("min_hours"), "Duración mínima", 0, 8760)
        maximum = stage.get("max_hours")
        if maximum is not None:
            number(maximum, "Duración máxima orientativa", minimum, 8760)
        if stage.get("exit") not in ("manual", "time", "attenuation", "stable"):
            raise ValueError("Condición inválida")
        if stage["exit"] == "attenuation":
            number(stage.get("attenuation_pct"), "Atenuación", 1, 100)
    if result.get("target_sg") is not None:
        checked_gravity(result["target_sg"])
    number(result.get("reading_max_age_hours", 24), "Vigencia de densidad", 1, 168)
    number(result.get("stability_hours", 48), "Ventana de estabilidad", 1, 168)
    number(result.get("stability_tolerance", 0.001), "Tolerancia SG", 0.0001, 0.010)
    return result


class ProfileStore(RecipeStore):
    def __init__(self, path, clock=None):
        super().__init__(path)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS recipe_catalog (id TEXT PRIMARY KEY, archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, fermenter TEXT NOT NULL,
          status TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_batch ON batches(fermenter)
          WHERE status IN ('active','paused');
        CREATE TABLE IF NOT EXISTS readings (id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
          measured_ms INTEGER NOT NULL, body TEXT NOT NULL, void_reason TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS reading_time ON readings(batch_id,measured_ms) WHERE void_reason IS NULL;
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, batch_id TEXT,
          at_ms INTEGER NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
        """)
        self.db.commit()

    def event(self, batch_id, kind, body):
        self.db.execute("INSERT INTO events(batch_id,at_ms,kind,body) VALUES(?,?,?,?)",
                        (batch_id, self.clock(), kind, json.dumps(body, ensure_ascii=False)))

    def batch(self, batch_id):
        row = self.db.execute("SELECT body FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise ValueError("Lote inexistente")
        return json.loads(row[0])

    def readings(self, batch_id):
        rows = self.db.execute("SELECT id,body,void_reason FROM readings WHERE batch_id=? ORDER BY measured_ms", (batch_id,))
        return [dict(json.loads(body), id=rid, void_reason=reason) for rid, body, reason in rows]

    def elapsed(self, batch):
        return batch["stage_elapsed_s"] + (max(0, self.clock() - batch["segment_started_ms"]) / 1000 if batch["segment_started_ms"] is not None else 0)

    def evaluate(self, batch):
        recipe = batch["recipe"]
        stage = recipe["stages"][batch["stage_index"]]
        elapsed = self.elapsed(batch)
        distance = stage["temperature_c"] - batch["anchor_c"]
        movement = stage["ramp_c_per_hour"] * elapsed / 3600
        calculated = batch["anchor_c"] + (1 if distance >= 0 else -1) * min(abs(distance), movement)
        readings = [r for r in self.readings(batch["id"]) if not r["void_reason"]]
        latest = readings[-1] if readings else None
        fresh = latest is not None and 0 <= self.clock() - latest["measured_ms"] <= recipe.get("reading_max_age_hours", 24) * 3600000
        attenuation = apparent_attenuation(batch["og"], latest["corrected_sg"]) if latest else None
        progress = target_progress(batch["og"], latest["corrected_sg"], recipe["target_sg"]) if latest and recipe.get("target_sg") is not None else None
        stable = False
        if fresh and all(r["measured_ms"] <= self.clock() for r in readings):
            stable = gravity_is_stable([GravityReading(datetime.fromtimestamp(r["measured_ms"] / 1000, timezone.utc), r["corrected_sg"]) for r in readings],
                                      datetime.fromtimestamp(self.clock() / 1000, timezone.utc),
                                      hours=recipe.get("stability_hours", 48), tolerance=recipe.get("stability_tolerance", 0.001))
        reasons = []
        if self.clock() < batch["started_ms"] or (batch["segment_started_ms"] is not None and self.clock() < batch["segment_started_ms"]):
            reasons.append("El reloj retrocedió; revisar antes de avanzar")
        if batch["status"] != "active":
            reasons.append("El lote no está activo")
        if elapsed < stage["min_hours"] * 3600:
            reasons.append("No se cumplió la duración mínima de la etapa")
        if stage["exit"] in ("attenuation", "stable") and not fresh:
            reasons.append("Falta una densidad corregida y vigente")
        if stage["exit"] == "attenuation" and fresh and attenuation < stage["attenuation_pct"]:
            reasons.append("Atenuación por debajo del criterio configurado")
        if stage["exit"] == "stable" and fresh and not stable:
            reasons.append("Todavía no hay estabilidad con cobertura temporal suficiente")
        next_stage = recipe["stages"][batch["stage_index"] + 1] if batch["stage_index"] + 1 < len(recipe["stages"]) else None
        # Todo ingreso a enfriado exige densidad vigente/estable y comprobación manual.
        if next_stage and next_stage["kind"] == "cooling":
            if not fresh or not stable:
                reasons.append("Para enfriar se requiere densidad vigente y estable")
            if batch.get("diacetyl", {}).get("status") != "approved":
                reasons.append("Falta aprobar la comprobación manual de diacetilo")
        return {"calculated_c": round(calculated, 3), "stage_elapsed_hours": round(elapsed / 3600, 3),
                "attenuation_pct": round(attenuation, 2) if attenuation is not None else None,
                "target_progress_pct": round(progress, 2) if progress is not None else None,
                "density_fresh": fresh, "density_stable": stable, "latest_density": latest,
                "transition_ready": not reasons, "reasons": reasons,
                "suggestion": ("Confirmar paso a " + next_stage["name"] if next_stage else "Confirmar cierre del lote") if not reasons else "Mantener etapa y revisar los criterios",
                "duration_warning": stage.get("max_hours") is not None and elapsed > stage["max_hours"] * 3600,
                "remote_commands_enabled": False}

    def command(self, request):
        rid = text(request.get("request_id"), "Identificador de operación", 100)
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            prior = self.db.execute("SELECT fingerprint,result FROM requests WHERE id=?", (rid,)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise Conflict("Identificador de operación reutilizado con otros datos")
                self.db.rollback()
                return json.loads(prior[1])
            result = self._command(request)
            self.db.execute("INSERT INTO requests VALUES(?,?,?)", (rid, fingerprint, json.dumps(result)))
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def _command(self, p):
        action = p.get("action")
        if action == "save_recipe":
            recipe = validate_staged_recipe(p.get("recipe", {}))
            if recipe.get("schema") != "staged-v1":
                raise ValueError("Esquema de receta inválido")
            recipe_id = text(p.get("recipe_id") or str(uuid.uuid4()), "ID de receta", 100)
            row = self.db.execute("SELECT COALESCE(MAX(version),0) FROM recipes WHERE recipe_id=?", (recipe_id,)).fetchone()
            if p.get("expected_version", 0) != row[0]:
                raise Conflict("La receta cambió: recargá antes de guardar")
            archived = self.db.execute("SELECT archived FROM recipe_catalog WHERE id=?", (recipe_id,)).fetchone()
            if archived and archived[0]:
                raise Conflict("La receta está archivada; duplicala para crear otra")
            version = row[0] + 1
            self.db.execute("INSERT INTO recipes VALUES(?,?,?)", (recipe_id, version, json.dumps(recipe, ensure_ascii=False)))
            self.db.execute("INSERT OR IGNORE INTO recipe_catalog VALUES(?,0)", (recipe_id,))
            self.event(None, action, {"recipe_id": recipe_id, "version": version})
            return {"recipe_id": recipe_id, "version": version}
        if action == "archive_recipe":
            recipe_id = text(p.get("recipe_id"), "ID de receta", 100)
            if not self.db.execute("SELECT 1 FROM recipe_catalog WHERE id=?", (recipe_id,)).fetchone():
                raise ValueError("Receta inexistente")
            self.db.execute("UPDATE recipe_catalog SET archived=1 WHERE id=?", (recipe_id,))
            self.event(None, action, {"recipe_id": recipe_id})
            return {"archived": True}
        if action == "start_batch":
            recipe_id = text(p.get("recipe_id"), "ID de receta", 100)
            version = p.get("version")
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ValueError("Seleccioná una versión de receta")
            row = self.db.execute("SELECT archived FROM recipe_catalog WHERE id=?", (recipe_id,)).fetchone()
            if not row or row[0]:
                raise ValueError("Receta ausente o archivada")
            recipe = self.load(recipe_id, version)
            if recipe.get("schema") != "staged-v1":
                raise ValueError("Convertí la receta anterior a etapas antes de iniciar")
            og = checked_gravity(p.get("og"))
            if og <= 1 or (recipe.get("target_sg") is not None and recipe["target_sg"] >= og):
                raise ValueError("Revisá OG y FG estimada")
            if p.get("classification") not in ("bench", "real"):
                raise ValueError("Clasificá el lote como banco o real")
            if p.get("fermenter") != "fermentador-1":
                raise ValueError("Esta instalación gestiona solamente fermentador-1")
            bid = str(uuid.uuid4())
            batch = {"id": bid, "name": text(p.get("name"), "Nombre de lote"), "fermenter": text(p.get("fermenter"), "Fermentador", 100),
                     "recipe_id": recipe_id, "recipe_version": version, "recipe": recipe, "og": og,
                     "initial_temperature_c": number(p.get("initial_temperature_c"), "Temperatura inicial", 0.1, 29.9),
                     "volume_l": number(p.get("volume_l"), "Volumen", 0.1, 10000), "classification": p["classification"],
                     "started_ms": self.clock(), "status": "active", "revision": 1, "stage_index": 0,
                     "stage_elapsed_s": 0, "segment_started_ms": self.clock(),
                     "anchor_c": p["initial_temperature_c"], "diacetyl": {"status": "pending"}}
            if recipe["stages"][0]["kind"] == "cooling":
                raise ValueError("El lote no puede comenzar directamente en enfriado")
            if self.db.execute("SELECT 1 FROM batches WHERE fermenter=? AND status IN ('active','paused')", (batch["fermenter"],)).fetchone():
                raise Conflict("Ese fermentador ya tiene un lote activo o pausado")
            self.db.execute("INSERT INTO batches VALUES(?,?,?,?,?)", (bid, batch["fermenter"], batch["status"], 1, json.dumps(batch)))
            self.event(bid, action, {"recipe_id": recipe_id, "version": version, "classification": batch["classification"], "initial_temperature_c": batch["anchor_c"]})
            return {"batch_id": bid, "revision": 1}
        batch = self.batch(p.get("batch_id"))
        if p.get("revision") != batch["revision"]:
            raise Conflict("El lote cambió: recargá antes de confirmar")
        if batch["status"] not in ("active", "paused"):
            raise Conflict("El lote está cerrado; su historial se conserva")
        details = {}
        if action == "pause":
            if batch["status"] != "active":
                raise Conflict("El lote ya está pausado")
            batch["stage_elapsed_s"] = self.elapsed(batch)
            batch["segment_started_ms"] = None
            batch["status"] = "paused"
        elif action == "resume":
            if batch["status"] != "paused":
                raise Conflict("El lote no está pausado")
            batch["segment_started_ms"] = self.clock()
            batch["status"] = "active"
        elif action in ("advance", "finish"):
            if p.get("confirm") is not True:
                raise ValueError("Se necesita confirmación manual")
            state = self.evaluate(batch)
            if not state["transition_ready"]:
                raise Conflict("; ".join(state["reasons"]))
            last = batch["stage_index"] == len(batch["recipe"]["stages"]) - 1
            if (action == "finish") != last:
                raise ValueError("Operación incompatible con la etapa actual")
            details = {"from_stage": batch["stage_index"], "reason": text(p.get("reason"), "Motivo", 1000), "evidence": state}
            if action == "finish":
                batch["stage_elapsed_s"] = self.elapsed(batch)
                batch["segment_started_ms"] = None
                batch["status"] = "finished"
                batch["finished_ms"] = self.clock()
            else:
                batch["anchor_c"] = state["calculated_c"]
                batch["stage_index"] += 1
                batch["stage_elapsed_s"] = 0
                batch["segment_started_ms"] = self.clock()
        elif action == "cancel":
            details = {"reason": text(p.get("reason"), "Motivo de cancelación", 1000)}
            batch["stage_elapsed_s"] = self.elapsed(batch)
            batch["segment_started_ms"] = None
            batch["status"] = "cancelled"
            batch["finished_ms"] = self.clock()
        elif action == "diacetyl":
            if p.get("status") not in ("pending", "approved", "failed", "not_performed"):
                raise ValueError("Resultado de comprobación inválido")
            batch["diacetyl"] = {"status": p["status"], "at_ms": self.clock(), "notes": text(p.get("notes"), "Observación", 1000)}
            details = batch["diacetyl"]
        elif action == "add_reading":
            sg = checked_gravity(p.get("corrected_sg"))
            if sg > batch["og"]:
                raise ValueError("La densidad supera OG; revisá la medición")
            if p.get("corrected") is not True:
                raise ValueError("Confirmá que la SG fue corregida para el instrumento")
            stamp = text(p.get("measured_at"), "Fecha con zona horaria", 50)
            date = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("La fecha necesita zona horaria")
            measured = int(date.timestamp() * 1000)
            if not batch["started_ms"] <= measured <= self.clock():
                raise ValueError("La medición debe estar entre el inicio del lote y el momento actual")
            details = {"corrected_sg": sg, "measured_ms": measured, "measured_at": stamp, "recorded_ms": self.clock(),
                       "instrument": text(p.get("instrument"), "Instrumento", 100),
                       "sample_temperature_c": number(p.get("sample_temperature_c"), "Temperatura de muestra", 0, 60),
                       "original_unit": "SG corregida", "notes": str(p.get("notes", ""))[:1000]}
            reading_id = str(uuid.uuid4())
            if self.db.execute("SELECT 1 FROM readings WHERE batch_id=? AND measured_ms=? AND void_reason IS NULL", (batch["id"], measured)).fetchone():
                raise Conflict("Ya existe una medición vigente para esa fecha")
            self.db.execute("INSERT INTO readings VALUES(?,?,?,?,NULL)", (reading_id, batch["id"], measured, json.dumps(details)))
            details = dict(details, reading_id=reading_id)
            # Una nueva lectura invalida aprobaciones anteriores: deben revisarse con los datos nuevos.
            batch["diacetyl"] = {"status": "pending"}
        elif action == "void_reading":
            reason = text(p.get("reason"), "Motivo de anulación", 1000)
            count = self.db.execute("UPDATE readings SET void_reason=? WHERE id=? AND batch_id=? AND void_reason IS NULL", (reason, p.get("reading_id"), batch["id"])).rowcount
            if not count:
                raise ValueError("Medición ausente o ya anulada")
            batch["diacetyl"] = {"status": "pending"}
            details = {"reading_id": p["reading_id"], "reason": reason}
        else:
            raise ValueError("Operación desconocida")
        batch["revision"] += 1
        self.db.execute("UPDATE batches SET status=?,revision=?,body=? WHERE id=?", (batch["status"], batch["revision"], json.dumps(batch), batch["id"]))
        self.event(batch["id"], action, details)
        return {"batch_id": batch["id"], "revision": batch["revision"]}

    def snapshot(self, selected=None):
        recipes = []
        for recipe_id, archived in self.db.execute("SELECT id,archived FROM recipe_catalog ORDER BY rowid DESC"):
            versions = [{"version": version, "recipe": json.loads(body)} for version, body in self.db.execute("SELECT version,body FROM recipes WHERE recipe_id=? ORDER BY version DESC", (recipe_id,))]
            recipes.append({"id": recipe_id, "archived": bool(archived), "versions": versions})
        batches = [{k: b[k] for k in ("id", "name", "status", "classification", "started_ms", "fermenter", "recipe_version")} for (body,) in self.db.execute("SELECT body FROM batches ORDER BY rowid DESC") for b in [json.loads(body)]]
        active = next((b["id"] for b in batches if b["status"] in ("active", "paused")), None)
        selected = selected or active or (batches[0]["id"] if batches else None)
        batch = self.batch(selected) if selected else None
        events = [dict(id=eid, at_ms=at, kind=kind, details=json.loads(body)) for eid, at, kind, body in self.db.execute("SELECT id,at_ms,kind,body FROM events WHERE batch_id IS ? ORDER BY id DESC LIMIT 200", (selected,))]
        return {"recipes": recipes, "batches": batches, "batch": batch, "evaluation": self.evaluate(batch) if batch else None,
                "readings": self.readings(selected) if selected else [], "events": events,
                "server_ms": self.clock(), "mode": "supervised", "remote_commands_enabled": False}

    def export(self, batch_id):
        result = self.snapshot(batch_id)
        result = {k: result[k] for k in ("batch", "evaluation", "readings", "server_ms")}
        result["events"] = [dict(id=eid, at_ms=at, kind=kind, details=json.loads(body)) for eid, at, kind, body in self.db.execute("SELECT id,at_ms,kind,body FROM events WHERE batch_id=? ORDER BY id", (batch_id,))]
        return result
