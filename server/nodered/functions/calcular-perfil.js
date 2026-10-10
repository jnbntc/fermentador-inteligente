// Interpolación del perfil existente; no es PID. La salida MQTT se bloquea en el parche.
const receta = flow.get("receta_activa", "file");
const inicio = flow.get("inicio_fermentacion", "file");
if (receta === undefined || inicio === undefined || inicio === null) {
    flow.set("estado_lote", undefined, "file");
    node.status({fill: "grey", shape: "ring", text: "Sin lote iniciado"});
    return null;
}
const now = Date.now();
const finite = x => typeof x === "number" && Number.isFinite(x);
let previous = -1;
let valid = Array.isArray(receta) && receta.length > 0 && finite(inicio) && inicio > 0 && inicio <= now;
if (valid) {
    for (const point of receta) {
        if (!point || !finite(point.dia) || !finite(point.temp) || point.dia < 0 || point.dia <= previous || point.temp <= 0 || point.temp >= 30) {
            valid = false;
            break;
        }
        previous = point.dia;
    }
    valid = valid && receta[0].dia === 0;
}
if (!valid) {
    flow.set("estado_lote", undefined, "file");
    node.error("Perfil o fecha de inicio inválidos; no se calcula consigna", {topic: "perfil"});
    node.status({fill: "red", shape: "ring", text: "Perfil inválido"});
    return null;
}
const days = (now - inicio) / 86400000;
const total = receta[receta.length - 1].dia;
let target = receta[receta.length - 1].temp;
for (let i = 0; i < receta.length - 1; i++) {
    const a = receta[i], b = receta[i + 1];
    if (days >= a.dia && days < b.dia) {
        target = a.temp + (b.temp - a.temp) * (days - a.dia) / (b.dia - a.dia);
        break;
    }
}
target = Math.round(target * 100) / 100;
if (!(target > 0 && target < 30)) {
    flow.set("estado_lote", undefined, "file");
    node.error("Consigna redondeada fuera del rango del ESP32", {topic: "perfil"});
    return null;
}
const state = {setpoint: target, transcurridos: Number(days.toFixed(2)),
    restantes: Number(Math.max(0, total - days).toFixed(2)), total, updated_at_ms: now};
// Guardar antes de cualquier retorno, aunque la consigna cambie en este tick.
flow.set("estado_lote", state, "file");
flow.set("dias_transcurridos", state.transcurridos, "file");
flow.set("dias_restantes", state.restantes, "file");
const last = flow.get("ultimo_setpoint", "file");
node.status({fill: "blue", shape: "dot", text: "Perfil calculado: " + target + " °C; salida remota bloqueada"});
// No actualiza ultimo_setpoint: calcular o intentar publicar no demuestra aplicación.
const changed = !finite(last) || Math.abs(target - last) >= 0.05;
return [changed ? {payload: String(target)} : null, {payload: state}];
