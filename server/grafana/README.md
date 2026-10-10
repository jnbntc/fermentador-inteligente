# Grafana: supervisión del fermentador

Dashboard clásico compatible con **Grafana 10.4.2**, desplegado el 10 de octubre de 2026. El ESP32 conserva todo el control local. Grafana solo consulta datos: no publica consignas, no activa relés y no incorpora ML.

**Ensayo de banco sin compresor; FASE D pendiente.** Las lecturas proceden del equipo de banco; el perfil y su progreso son datos de prueba, no una fermentación real.

## Qué se corrigió

El archivo anterior era un recurso de Grafana 13 (`kind/spec`), incompatible con el aprovisionamiento de Grafana 10.4.2. Provocaba «Dashboard title cannot be empty» cada diez segundos. Ahora se usa el modelo clásico con título en la raíz y `schemaVersion: 39`.

Se conservaron el UID y título del dashboard existente, los IDs de sus tres paneles originales y el datasource ya configurado. No se copiaron tokens al repositorio ni se cambiaron usuarios, contraseñas o permisos de acceso.

| Vista | Fuente y significado |
|---|---|
| MOSTO | Última lectura válida del sobre más reciente; no recupera una lectura vieja si el último sobre informa falla |
| Consigna aplicada | `fermentador.setpoint_applied`; admite el alias histórico `setpoint` del mismo sobre |
| Desvío | MOSTO menos consigna aplicada del mismo timestamp; no es una medida completa del rendimiento del control |
| Controlador | Estado informado por el ESP32; COOLING expresa una orden, no refrigeración comprobada |
| Edad de telemetría | Segundos desde la última muestra hasta el final del intervalo seleccionado |
| Curva térmica | MOSTO, AMBIENTE y consigna aplicada; excluye lecturas fuera de rango físico |
| Sensores y conexión | Flags de sondas, conexión y salida del relé del último informe |
| Perfil de prueba | Consigna calculada y días publicados por Node-RED en `estado_orquestador`; no usa la primera medición como inicio de lote |
| Diagnóstico | Uptime, secuencia, ciclos, histéresis, protección y máximo intervalo del control |

El perfil calculado puede mostrar 3 °C mientras el ESP32 aplica 18 °C. Son conceptos diferentes; la publicación remota continúa bloqueada en Node-RED.

## Vigencia e historia

Todas las consultas respetan el intervalo seleccionado. Las tarjetas y tablas actuales solo aceptan muestras hasta **900 segundos** anteriores al cierre del intervalo. Sin una muestra vigente muestran ausencia de datos, sin inventar ceros. La edad de la telemetría permanece visible y pasa a rojo desde 900 segundos. En una vista histórica esa edad se evalúa al final del intervalo histórico, no respecto a la hora actual.

Los flags Wi-Fi/MQTT describen el último informe recibido. Durante una desconexión no llega un informe nuevo que confirme el estado actual: se debe observar también la edad de la telemetría. El dashboard no infiere una conexión activa a partir de un valor histórico.

La curva usa un intervalo mínimo de 10 s, acorde con la cadencia del dispositivo, y promedia temperaturas por ventana; conserva huecos vacíos y no conecta temperaturas a través de nulls. La consigna usa el último valor por ventana y escalones, sin promediar consignas. Los flags de validez se consideran en las tarjetas actuales. Para la historia antigua se filtran los rangos físicos; no se atribuyen flags que no existían.

El contrato actual contempla un fermentador. Antes de agregar equipos o lotes reales se necesitan tags de identidad, separación de datos de banco y un modelo de lotes/densidades. No se añadieron densidad, atenuación, diacetilo ni predicciones al dashboard porque todavía no existen esas mediciones integradas.

## Archivos y comprobaciones

- `dashboard.json`: plantilla importable. Solicita seleccionar un datasource InfluxDB Flux mediante `DS_INFLUXDB`.
- `build_dashboard.py`: genera la plantilla y las consultas `queries/*.flux` sin dependencias externas.
- `render_dashboard.py`: resuelve los UIDs para aprovisionamiento por archivos; no requiere tokens.
- `manage.py` y `scripts/`: respaldo privado y migración inicial del aprovisionamiento existente. Requieren SSH con clave y Docker en el servidor.
- `test_dashboard.py`: seis comprobaciones de formato, reproducibilidad, UIDs, geometría, unidades y política de huecos.

```bash
python3 server/grafana/build_dashboard.py
python3 -m unittest discover -s server/grafana -p 'test_*.py' -v
```

Además de los tests locales, durante el despliegue se ejecutaron **30 consultas de lectura** contra InfluxDB: diez consultas en intervalo real, intervalo vacío y cierre futuro para simular antigüedad. Todas respondieron HTTP 200; se comprobaron filas reales en los paneles principales y las cinco filas de sensores, ausencia de valores inventados en intervalos vacíos y ausencia de valores vigentes con muestras vencidas. No se insertaron muestras sintéticas ni se interrumpió la red para esas comprobaciones.

La comprobación visual verifica también el render: un HTTP 200 por sí solo no garantiza una visualización correcta. Los tests aislados no acceden al servidor doméstico. Se incluye una plantilla de Actions sin activar; la autorización de publicación actual no tiene permiso para escribir workflows.

## Respaldo y despliegue

La migración del servidor dejó el aprovisionamiento en `/opt/telemetria_birra/grafana-provisioning`, montado **de solo lectura** en `/etc/grafana/provisioning`. Conservó el proveedor `OMBU-Telemetria` y su carpeta de dashboards. La base de datos permanece en el volumen de datos original.

Antes de migrar se copian datos, configuración completa de `/etc/grafana`, Compose y metadatos de recuperación a `$HOME/.local/state/fermentador/backups/grafana-<UTC>`, con directorio 0700 y archivo 0600. El respaldo incluye información privada de usuarios y credenciales cifradas: **no subirlo a GitHub**. Se pausa brevemente solo Grafana durante la copia de datos; se comprueban SQLite y el hash del archivo archivado. El estado volátil del proceso no se respalda.

Ejemplo de respaldo, reemplazando el destino y la clave por los propios:

```bash
python3 server/grafana/manage.py backup \
  --host usuario@servidor \
  --identity ~/.ssh/id_ed25519 \
  --output /tmp/grafana-backup-metadata.json
```

La acción `migrate` es **solo para la migración inicial** desde la instalación sin volumen de provisioning. Requiere un respaldo recién creado y el UID existente; verifica cambios concurrentes, conserva datasource/credenciales y comprueba que Compose solo agregue el volumen de Grafana. Recrea únicamente Grafana con la misma imagen, sin descargar otra versión. Rechaza una instalación ya migrada; no usarla como actualizador genérico.

```bash
python3 server/grafana/manage.py migrate \
  --host usuario@servidor \
  --identity ~/.ssh/id_ed25519 \
  --backup /ruta/remota/devuelta/por/backup \
  --dashboard-uid UID_EXISTENTE
```

Para actualizar una instalación ya migrada, generar el JSON con los UIDs existentes, comparar el archivo activo y sus cambios de UI, respaldar y sustituir atómicamente solo el archivo del dashboard. El proveedor lo relee cada diez segundos; no requiere recrear el servicio. No copiar la plantilla sin resolver el datasource:

```bash
python3 server/grafana/render_dashboard.py \
  --datasource-uid UID_INFLUXDB_EXISTENTE \
  --dashboard-uid UID_DASHBOARD_EXISTENTE \
  --output /tmp/dashboard-resuelto.json
```

Los cambios hechos en la UI pueden diferir del archivo versionado: antes de sustituirlo hay que revisar esos cambios. La migración inicial aborta si el dashboard o Compose cambian desde el respaldo.

## Recuperación

El respaldo privado conserva la base, provisioning original, configuración y Compose original. Para una recuperación completa: detener únicamente Grafana, conservar el estado actual en otra ubicación privada, restaurar datos/configuración/Compose del respaldo con sus propietarios y permisos correctos, recrear solo Grafana y comprobar `/api/health`, usuarios, datasource y dashboards. Evitar una restauración de base mientras el servicio escribe o si descartaría cambios posteriores sin revisar.

Restaurar el provisioning antiguo vuelve a introducir su formato incompatible. Una recuperación funcional puede utilizar la definición clásica original guardada en `dashboards.private.json` en vez del recurso incompatible, tras revisar cuál estado se desea recuperar. No se necesitó rollback ni se ensayó una restauración completa.

Ver [registro del despliegue](../../docs/SERVER_DEPLOYMENT.md). Referencias: [aprovisionamiento de Grafana 10.4](https://archive.grafana.com/docs/grafana/v10.4/administration/provisioning/) y [modelo JSON de dashboards](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/view-dashboard-json-model/).
