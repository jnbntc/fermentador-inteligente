const existing = flow.get("inicio_fermentacion", "file");
if (existing !== undefined && existing !== null) {
    node.error("Ya existe un lote iniciado; no se reemplaza su fecha", {topic: "lote"});
    return null;
}
const now = Date.now();
flow.set("inicio_fermentacion", now, "file");
flow.set("ultimo_setpoint", null, "file");
flow.set("estado_lote", undefined, "file");
msg.payload = "Lote iniciado: " + new Date(now).toISOString();
return msg;
