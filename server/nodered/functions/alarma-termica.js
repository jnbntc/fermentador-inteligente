const p = msg.payload;
if (!p || p.mosto_valid !== true || !Number.isFinite(p.mosto) || !Number.isFinite(p.setpoint_applied)) return null;
const configured = env.get("THERMAL_ALERT_DELTA_C");
const threshold = configured === undefined || configured === "" ? 20 : Number(configured);
if (!Number.isFinite(threshold) || threshold <= 0 || threshold > 30) {
    node.error("THERMAL_ALERT_DELTA_C debe ser mayor que 0 y no mayor que 30", {topic: "alarma-termica"});
    return null;
}
const delta = Math.abs(p.mosto - p.setpoint_applied);
if (delta < threshold) return null;
return {payload: "Desvío térmico: MOSTO " + p.mosto + " °C; consigna aplicada " + p.setpoint_applied + " °C; diferencia " + delta.toFixed(2) + " °C. Revisar el sistema."};
