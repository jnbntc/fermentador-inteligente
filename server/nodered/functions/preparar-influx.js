// Solo recibe mensajes de validar-telemetria. No escribe null ni objetos en Influx.
const source = msg.payload;
if (!source || typeof source !== "object" || Array.isArray(source)) return null;
const fields = {};
const numbers = ["mosto", "ambiente", "setpoint", "setpoint_desired", "setpoint_applied", "hysteresis", "rele",
    "lockout_remaining_s", "uptime_s", "message_seq", "control_cycles", "setpoint_rejections", "control_max_gap_ms",
    "wifi_losses", "mqtt_losses", "dropped_logs", "dropped_commands"];
for (const key of numbers) {
    if ((key === "mosto" || key === "ambiente") && source[key + "_valid"] !== true) continue;
    if (typeof source[key] === "number" && Number.isFinite(source[key])) fields[key] = source[key];
}
for (const key of ["mosto_valid", "ambiente_valid", "relay", "wifi", "mqtt", "degraded", "dry_run", "cooling_request", "cooling_active"]) {
    if (typeof source[key] === "boolean") fields[key] = source[key];
}
for (const key of ["controller_state", "mosto_fault", "ambiente_fault", "fault"]) {
    if (typeof source[key] === "string") fields[key] = source[key];
}
const state = flow.get("estado_lote", "file");
if (state && typeof state === "object") {
    for (const [field, key] of [["dias_trans", "transcurridos"], ["dias_rest", "restantes"]]) {
        if (typeof state[key] === "number" && Number.isFinite(state[key]) && state[key] >= 0) fields[field] = state[key];
    }
} // Sin lote calculado no inventa progreso cero.
msg.payload = fields;
return msg;
