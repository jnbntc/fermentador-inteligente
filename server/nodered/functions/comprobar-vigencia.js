// Tick independiente: funciona incluso si nunca llegó telemetría tras arrancar.
const now = Date.now();
let started = context.get("startedAt");
if (!Number.isFinite(started)) { started = now; context.set("startedAt", started); }
const configured = env.get("TELEMETRIA_TIMEOUT_S");
const seconds = configured === undefined || configured === "" ? 900 : Number(configured);
if (!Number.isFinite(seconds) || seconds < 30 || seconds > 86400) {
    node.error("TELEMETRIA_TIMEOUT_S debe estar entre 30 y 86400", {topic: "vigencia"});
    return null;
}
const received = flow.get("telemetria_recibida_ms");
const reference = Number.isFinite(received) && received >= started && received <= now ? received : started;
const offline = now - reference >= seconds * 1000;
node.status({fill: offline ? "yellow" : "green", shape: offline ? "ring" : "dot", text: offline ? "Sin telemetría vigente" : "Esperando / recepción vigente"});
const before = context.get("offline") === true;
context.set("offline", offline);
if (before === offline) return null;
return {topic: "fermentador/diagnostico", payload: {event: offline ? "TELEMETRIA_AUSENTE" : "TELEMETRIA_RECUPERADA", received_at_ms: Number.isFinite(received) ? received : null, checked_at_ms: now}};
