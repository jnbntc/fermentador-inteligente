"""Parche aditivo: página del Dashboard y proxy interno, sin publicar consignas."""
import copy

TAB = "profiles_v1_tab"


def build(source, base_sha256):
    by_id = {n["id"]: n for n in source}
    if TAB in by_id:
        raise ValueError("El gestor ya está instalado; revisar una actualización por separado")
    bases = [n for n in source if n["type"] == "ui-base"]
    pages = [n for n in source if n["type"] == "ui-page"]
    if len(bases) != 1 or not pages or "nr10_validar" not in by_id:
        raise ValueError("No se reconoce el Dashboard o la validación de telemetría")
    additions = [dict(id=TAB, type="tab", label="Gestión de recetas y lotes · supervisada", disabled=False,
                      info="SQLite transaccional. Las propuestas nunca se conectan a MQTT ni al relé.")]

    def function(nid, name, code, x, y, wires):
        additions.append(dict(id=nid, type="function", z=TAB, name=name, func=code, outputs=1,
                              noerr=0, initialize="", finalize="", libs=[], x=x, y=y, wires=wires))

    for nid, method, route, target, y in [
        ("page", "get", "/perfiles", "/", 80),
        ("page_slash", "get", "/perfiles/", "/", 140),
        ("get", "get", "/perfiles/api", "/api", 200),
        ("export", "get", "/perfiles/export", "/export", 260),
        ("post", "post", "/perfiles/api", "/api", 320),
    ]:
        additions.append(dict(id="profiles_in_"+nid, type="http in", z=TAB, name=method.upper()+" "+route,
                              url=route, method=method, upload=False, swaggerDoc="", x=160, y=y,
                              wires=[["profiles_prepare_"+nid]]))
        guard = """
const origin = msg.req.headers.origin;
let sameOrigin = false;
try { sameOrigin = new URL(origin).host === msg.req.headers.host; } catch (_) {}
if (!sameOrigin || msg.req.headers['x-perfiles-request'] !== '1' ||
    !(msg.req.headers['content-type'] || '').startsWith('application/json')) {
    msg.statusCode = 403; msg.payload = JSON.stringify({error:'Solicitud de otro origen o sin protección de formulario'});
    msg.headers = {'content-type':'application/json'};
    node.send([null, msg]); return null;
}
""" if method == "post" else ""
        # URL is provided by the Function sandbox in Node-RED; no module installation.
        guard = guard.replace("new URL(origin).host === msg.req.headers.host", "typeof origin === 'string' && (origin === 'http://' + msg.req.headers.host || origin === 'https://' + msg.req.headers.host)")
        code = guard + "\nmsg.method = " + repr(method.upper()) + ";\nmsg.url = 'http://birra_perfiles:8787"+target+"';\n"
        if nid in ("get", "export"):
            code += "if (typeof msg.req.query.batch === 'string') msg.url += '?batch=' + encodeURIComponent(msg.req.query.batch);\n"
        if method == "get":
            code += "msg.payload = undefined;\n"
        code += "msg.headers = {'content-type':'application/json'};\nreturn msg;"
        function("profiles_prepare_"+nid, "Preparar petición interna", code, 470, y, [["profiles_http"]])
        if method == "post":
            additions[-1]["outputs"] = 2
            additions[-1]["wires"] = [["profiles_http"], ["profiles_response"]]
    additions.append(dict(id="profiles_http", type="http request", z=TAB, name="Gestor SQLite interno",
                          method="use", ret="txt", paytoqs="ignore", url="", tls="", persist=False, proxy="", insecureHTTPParser=False,
                          authType="", senderr=False, headers=[], requestTimeout="5000", x=740, y=200, wires=[["profiles_headers"]]))
    function("profiles_headers", "Respuesta sin caché", """msg.headers = {'content-type':msg.headers?.['content-type'] || 'application/json',
 'cache-control':'no-store','x-content-type-options':'nosniff', 'content-security-policy':"frame-ancestors 'self'"};
if (typeof msg.statusCode !== 'number') { msg.statusCode=503; msg.payload=JSON.stringify({error:'Gestor temporalmente sin conexión'}); }
return msg;""", 990, 200, [["profiles_response"]])
    additions.append(dict(id="profiles_response", type="http response", z=TAB, name="Responder al navegador", statusCode="",
                          headers={}, x=1230, y=200, wires=[]))
    function("profiles_telemetry", "Copiar telemetría validada · sin comandos", """msg = {payload: msg.payload};
msg.headers = {'content-type':'application/json'};
return msg;""", 300, 440, [["profiles_telemetry_http"]])
    additions.append(dict(id="profiles_telemetry_http", type="http request", z=TAB, name="MOSTO y consigna aplicada al gestor",
                          method="POST", ret="txt", paytoqs="ignore", url="http://birra_perfiles:8787/telemetry", tls="", persist=False,
                          proxy="", insecureHTTPParser=False, authType="", senderr=False, headers=[], requestTimeout="3000",
                          x=760, y=440, wires=[[]]))
    additions.append(dict(id="profiles_catch", type="catch", z=TAB, name="Errores de peticiones", scope=["profiles_http"],
                          uncaught=False, x=300, y=540, wires=[["profiles_unavailable"]]))
    function("profiles_unavailable", "Informar indisponibilidad sin ejecutar acciones", """if (!msg.res) return null;
msg.statusCode=503; msg.payload=JSON.stringify({error:'Gestor temporalmente sin conexión; no se confirmó la operación'});
msg.headers={'content-type':'application/json','cache-control':'no-store'};return msg;""", 770, 540, [["profiles_response"]])
    page = dict(id="profiles_ui_page", type="ui-page", name="Recetas y lotes", ui=bases[0]["id"], path="/perfiles", icon="book-open-variant",
                layout="grid", theme=pages[0]["theme"], breakpoints=copy.deepcopy(pages[0]["breakpoints"]), order=2,
                className="", visible="true", disabled="false")
    additions.extend([page, dict(id="profiles_ui_group", type="ui-group", name="Gestión supervisada", page=page["id"],
                                width=12, height=1, order=1, showTitle=False, className="", visible=True, disabled=False, groupType="default"),
                      dict(id="profiles_ui_template", type="ui-template", z=TAB, group="profiles_ui_group", page="", ui="", name="Catálogo, lotes y mediciones",
                           order=1, width="12", height="12", head="", format='<template><iframe src="/perfiles" title="Gestión de recetas y lotes" style="width:100%;height:calc(100vh - 150px);min-height:700px;border:0;border-radius:8px"></iframe></template>',
                           storeOutMessages=False, passthru=False, resendOnRefresh=False, templateScope="local", className="", x=510, y=640, wires=[[]])])
    wires = copy.deepcopy(by_id["nr10_validar"]["wires"])
    wires[0].append("profiles_telemetry")
    return {"base_disk_sha256": base_sha256, "updates": {"nr10_validar": {"wires": wires}}, "additions": additions}
