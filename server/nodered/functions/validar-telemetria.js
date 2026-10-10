// Cuerpo de Function Node. No publica MQTT ni controla el relé.
function reject(reason) {
    node.error("Telemetría rechazada: " + reason, {topic: msg.topic});
    return null;
}
let p = msg.payload;
if (msg.retain === true) return reject("mensaje retenido sin fecha verificable");
if (Buffer.isBuffer(p)) p = p.toString("utf8");
if (typeof p === "string") {
    try { p = JSON.parse(p); } catch (_) { return reject("JSON inválido"); }
}
if (!p || typeof p !== "object" || Array.isArray(p)) return reject("se esperaba un objeto");
p = Object.assign({}, p);
const finite = v => typeof v === "number" && Number.isFinite(v);
const applied = p.setpoint_applied === undefined ? p.setpoint : p.setpoint_applied;
if (!finite(applied) || applied <= 0 || applied >= 30) return reject("consigna aplicada inválida");
const relay = p.relay === undefined ? p.rele === 1 ? true : p.rele === 0 ? false : undefined : p.relay;
if (typeof relay !== "boolean") return reject("estado del relé inválido");
for (const role of ["mosto", "ambiente"]) {
    const flag = role + "_valid";
    if (p[flag] !== undefined && typeof p[flag] !== "boolean") return reject("validez de sensor mal formada");
    const min = role === "mosto" ? -5 : -20;
    const max = role === "mosto" ? 40 : 60;
    const plausible = finite(p[role]) && p[role] >= min && p[role] <= max;
    // Compatibilidad con mensajes antiguos sin flags. Nunca convierte null a cero.
    p[flag] = plausible && p[flag] !== false;
    if (!p[flag]) p[role] = null;
}
for (const key of ["wifi", "mqtt", "dry_run", "degraded", "cooling_request", "cooling_active"]) {
    if (p[key] !== undefined && typeof p[key] !== "boolean") return reject("campo booleano mal formado: " + key);
}
if (p.setpoint_desired !== undefined && !finite(p.setpoint_desired)) return reject("consigna deseada no finita");
if (p.hysteresis !== undefined && (!finite(p.hysteresis) || p.hysteresis <= 0)) return reject("histéresis inválida");
p.setpoint_applied = applied;
p.setpoint = applied;
p.relay = relay;
p.rele = relay ? 1 : 0; // Mantiene el alias numérico usado por el firmware y Grafana.
msg.payload = p;
flow.set("telemetria_recibida_ms", Date.now()); // Memoria: una recepción anterior al reinicio no prueba presencia actual.
node.status({fill: p.mosto_valid ? "green" : "yellow", shape: "dot", text: p.mosto_valid ? "Telemetría válida" : "MOSTO inválido; evento conservado"});
return msg;
