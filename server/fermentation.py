"""Cálculos y catálogo versionado. Densidades SG previamente corregidas.

Este módulo no publica consignas ni determina la eliminación de diacetilo.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
import sqlite3


def checked_gravity(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("La densidad debe ser un número SG.")
    if not math.isfinite(value) or not 0.990 <= value <= 1.200:
        raise ValueError("Densidad fuera del rango admitido para esta aplicación.")
    return float(value)


def apparent_attenuation(original_sg, current_sg):
    original_sg, current_sg = map(checked_gravity, (original_sg, current_sg))
    if original_sg <= 1.0 or current_sg > original_sg:
        raise ValueError("Revisar densidad inicial y medición actual.")
    return 100.0 * (original_sg - current_sg) / (original_sg - 1.0)


def target_progress(original_sg, current_sg, target_sg):
    """Avance hacia una FG estimada; no es una garantía de finalización."""
    original_sg, current_sg, target_sg = map(
        checked_gravity, (original_sg, current_sg, target_sg)
    )
    if target_sg >= original_sg or current_sg > original_sg:
        raise ValueError("La FG objetivo debe ser menor que la densidad inicial.")
    return 100.0 * (original_sg - current_sg) / (original_sg - target_sg)


@dataclass(frozen=True)
class GravityReading:
    measured_at: datetime
    corrected_sg: float

    def __post_init__(self):
        checked_gravity(self.corrected_sg)
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("La medición necesita fecha y zona horaria.")


def gravity_is_stable(readings, now, hours=48, tolerance=0.001, min_readings=3):
    """Ejemplo configurable de estabilidad; nunca habilita por sí solo el enfriado.

    Exige cobertura del intervalo, una lectura reciente y timestamps distintos.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("El reloj necesita zona horaria.")
    if hours <= 0 or tolerance < 0 or not math.isfinite(tolerance) or min_readings < 2:
        raise ValueError("Criterio de estabilidad inválido.")
    samples = sorted(readings, key=lambda r: r.measured_at)
    if any(r.measured_at > now for r in samples):
        raise ValueError("Hay mediciones fechadas en el futuro.")
    cutoff = now - timedelta(hours=hours)
    # Una lectura anterior al inicio establece la referencia de la ventana.
    before = [r for r in samples if r.measured_at <= cutoff]
    recent = [r for r in samples if r.measured_at > cutoff]
    if not before or not recent:
        return False
    selected = [before[-1]] + recent
    times = {r.measured_at for r in selected}
    if len(times) != len(selected) or len(times) < min_readings:
        return False
    max_gap = timedelta(hours=hours / (min_readings - 1))
    if now - selected[-1].measured_at > max_gap:
        return False
    if any(b.measured_at - a.measured_at > max_gap for a, b in zip(selected, selected[1:])):
        return False
    values = [r.corrected_sg for r in selected]
    return max(values) - min(values) <= tolerance + 1e-12


def validate_recipe(recipe):
    if not isinstance(recipe, dict):
        raise ValueError("La receta debe ser un objeto.")
    if not isinstance(recipe.get("name"), str) or not recipe["name"].strip():
        raise ValueError("La receta necesita nombre.")
    stages = recipe.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("La receta necesita etapas.")
    if recipe.get("schema") == "staged-v1":
        from server.profiles.store import validate_staged_recipe
        return validate_staged_recipe(recipe)
    previous = -1
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("Etapa inválida.")
        day, temp = stage.get("day"), stage.get("temperature_c")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (day, temp)):
            raise ValueError("Días y temperaturas deben ser números finitos.")
        if day < 0 or day <= previous or not 0 < temp < 30:
            raise ValueError("Etapas desordenadas o temperatura no admitida por el firmware.")
        previous = day
    if stages[0]["day"] != 0:
        raise ValueError("La primera etapa debe comenzar en el día cero.")
    # La copia desacopla la receta guardada de cambios posteriores del llamador.
    return json.loads(json.dumps(recipe, allow_nan=False))


class RecipeStore:
    """Cada guardado crea una versión; una receta usada puede referenciarse sin cambios."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS recipes (
            recipe_id TEXT NOT NULL, version INTEGER NOT NULL,
            body TEXT NOT NULL, PRIMARY KEY(recipe_id, version)
        )""")
        self.db.commit()

    def close(self):
        self.db.close()

    def save(self, recipe_id, recipe):
        if not isinstance(recipe_id, str) or not recipe_id.strip():
            raise ValueError("La receta necesita un identificador.")
        body = json.dumps(validate_recipe(recipe), ensure_ascii=False)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            version = self.db.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM recipes WHERE recipe_id=?", (recipe_id,)
            ).fetchone()[0]
            self.db.execute("INSERT INTO recipes VALUES (?, ?, ?)", (recipe_id, version, body))
            self.db.commit()
            return version
        except Exception:
            self.db.rollback()
            raise

    def load(self, recipe_id, version=None):
        if version is None:
            row = self.db.execute(
                "SELECT body FROM recipes WHERE recipe_id=? ORDER BY version DESC LIMIT 1", (recipe_id,)
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT body FROM recipes WHERE recipe_id=? AND version=?", (recipe_id, version)
            ).fetchone()
        if row is None:
            raise KeyError((recipe_id, version))
        return json.loads(row[0])

    def list_versions(self):
        return self.db.execute("SELECT recipe_id, version FROM recipes ORDER BY recipe_id, version").fetchall()
