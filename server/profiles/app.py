"""HTTP interno, biblioteca estándar. Publicado solo a través de Node-RED."""
import argparse
import json
import sqlite3
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from server.profiles.store import ProfileStore, Conflict


def serve(database, bind="0.0.0.0", port=8787):
    store = ProfileStore(database)
    telemetry = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No se registran nombres de lotes ni mediciones en logs HTTP.

        def send(self, status, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                route = urlsplit(self.path)
                query = parse_qs(route.query)
                if route.path == "/health":
                    return self.send(200, {"status": "ok", "schema": "staged-v1", "remote_commands_enabled": False})
                if route.path == "/":
                    return self.send(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
                if route.path == "/api":
                    data = store.snapshot(query.get("batch", [None])[0])
                    data["telemetry"] = dict(telemetry)
                    data["telemetry"]["fresh"] = bool(telemetry) and time.monotonic() - telemetry["received_monotonic"] < 900
                    data["telemetry"].pop("received_monotonic", None)
                    return self.send(200, data)
                if route.path == "/export":
                    return self.send(200, store.export(query.get("batch", [""])[0]))
                self.send(404, {"error": "Ruta inexistente"})
            except (ValueError, KeyError, TypeError) as error:
                self.send(400, {"error": str(error)})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    return self.send(413, {"error": "Tamaño de solicitud no admitido"})
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.send(415, {"error": "Se necesita JSON"})
                data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Número no finito")))
                if not isinstance(data, dict):
                    raise ValueError("Se necesita un objeto")
                if self.path == "/api":
                    return self.send(200, store.command(data))
                if self.path == "/telemetry":
                    # Solo llega la rama validada de Node-RED; se conserva el último paquete completo.
                    fields = ("mosto", "ambiente", "mosto_valid", "ambiente_valid", "setpoint_applied", "relay", "wifi", "mqtt", "controller_state", "uptime_s", "message_seq")
                    telemetry.clear()
                    telemetry.update({key: data[key] for key in fields if key in data})
                    telemetry.update(received_ms=int(time.time() * 1000), received_monotonic=time.monotonic())
                    return self.send(200, {"received": True})
                self.send(404, {"error": "Ruta inexistente"})
            except Conflict as error:
                self.send(409, {"error": str(error)})
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                self.send(400, {"error": str(error)})
            except sqlite3.Error:
                self.send(503, {"error": "No se pudo confirmar la operación en la base; recargá antes de reintentar"})

    HTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="/data/profiles.sqlite")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    serve(args.database, args.bind, args.port)
