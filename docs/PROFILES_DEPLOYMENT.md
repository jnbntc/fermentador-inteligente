# Gestor de perfiles: despliegue del 10 de octubre de 2026

Se implementó y desplegó el gestor supervisado de recetas y lotes en **Node-RED Dashboard → Recetas y lotes**. Las propuestas no se publican al ESP32. **Ensayo de banco sin compresor; refrigeración real pendiente: FASE D.**

## Entrega

- Catálogo SQLite de recetas versionadas: crear, editar como nueva versión, duplicar y archivar.
- Lotes con copia independiente de receta, versión, OG corregida, temperatura inicial real, volumen y clasificación banco/real. Solo un lote activo/pausado para el fermentador existente.
- Etapas con objetivo térmico, rampa máxima, duración mínima/máxima orientativa y criterios de tiempo, atenuación o estabilidad. Pausa y reanudación conservan la rampa. Cambios de etapa y cierre requieren confirmación manual con motivo.
- Densidades corregidas con fechas de medición/registro, instrumento y temperatura de muestra. Anulación con motivo sin borrar el original.
- Comprobación manual de diacetilo y bloqueo del ingreso a enfriado sin estabilidad y aprobación. Una medición nueva invalida la aprobación anterior para revisar los datos.
- Historial por lote y exportación completa JSON. Consignas propuesta/aplicada separadas, sin atribuir al calendario un avance biológico.

## Despliegue y respaldo

Se verificaron primero los flujos activos de Node-RED: SHA-256 `6c550fd7f61aa44a30f300cd28ff09207300be373d0bab89855d66d83bc4c021`, 48 nodos. Se conservaron los ajustes del usuario en la receta de prueba anterior y posiciones del editor.

El respaldo privado anterior a la instalación es `nodered-20261010T141627Z`: archivo de 181.980.119 bytes, SHA-256 `e6e2f2ff0081842b880e57e99d533c2749d03bec85542ec61209f0d843b7cee4`. Se verificaron los seis archivos críticos y la revisión; pausa de Node-RED de 7,42 s, con reanudación garantizada. Los nombres de respaldo usan UTC.

Se agregó un servicio Python interno, con imagen local fijada por ID, usuario 1000, sistema de archivos raíz de solo lectura y datos persistentes. No publica puertos en el host, no descarga imágenes y no reemplaza el agente anterior. El servidor HTTP usa biblioteca estándar; no se instalaron módulos en Node-RED.

La API v2 de Node-RED aplicó una revisión concurrente del parche. Hay 69 nodos: los originales más 21 nuevos. Del grafo anterior solo cambió una conexión adicional desde `nr10_validar`; Clima, configuraciones compartidas y credenciales se conservaron. El SHA-256 final de flujos es `2665c64ac1c37af0a59ff97c04a0ab0d3519f57d7d285174daa630a77b418d6a`.

Los contenedores originales de Node-RED, Grafana, MQTT e InfluxDB conservaron sus IDs durante la instalación. Solo se creó/recreó el servicio nuevo de perfiles. Los cuatro bloqueos existentes permanecen activos: consignas MQTT, Telegram, Inject antiguo de inicio y watchdog antiguo. No se reinició ni cargó firmware en el ESP32.

Antes de un ajuste del servicio se generó `nodered-20261010T141842Z`: 181.985.204 bytes, SHA-256 `2696bbd987e189d7d1eec3342e0b76f9c48b66d593f5d3020acfb6487c7b243b`, pausa de 7,31 s. Este respaldo incluye también el gestor y una copia consistente de SQLite. El ajuste final de HTML usó `perfiles-assets-20261010T142532Z`, sin pausa ni reinicio; su copia SQLite tiene SHA-256 `c7473f34af6d0262ff8d4dd1850fc63843ce1007e8e592b6f36a0521b0bce7d2`.

Todos los respaldos permanecen privados en el servidor, bajo `$HOME/.local/state/fermentador/backups/`. No se publicaron bases, credenciales, SSID, direcciones privadas ni sesiones.

El estado final, incluida la receta archivada y el lote cancelado, tiene un snapshot completo del gestor `perfiles-20261010T143059Z`, sin pausa de servicios. Integridad SQLite correcta; SHA-256 de su copia: `7389bc5d4222d87ad2493b39b9248a1ddd6cc838b52c79e130745a38c80256b6`. El manifest privado incluye los hashes de código y configuración para recuperación.

## Verificación

| Evidencia | Resultado |
|---|---|
| Pruebas Python locales | 14 casos nuevos de perfiles y seis de la biblioteca anterior aprobados |
| Python del servicio desplegado | Los 14 casos nuevos aprobados usando SQLite temporal separado del activo |
| Proxy Node-RED | Grafo preservado, sin nuevas salidas de control, cuatro rechazos CSRF y una petición válida |
| Protección HTTP real | POST sin Origin/cabecera propia rechazado con HTTP 403 |
| Interfaz real | Alta de receta v1, lote fijado a v1, guardado de v2, densidad, pausa/reanudación, transición manual, bloqueo de cierre por falta de estabilidad y cancelación/archivo |
| Persistencia real | Reinicio solo del servicio de perfiles mientras el lote estaba pausado: lote, medición, eventos y consigna propuesta conservados exactamente |
| Exportación | Endpoint JSON comparado con el lote y sus seis eventos/una medición; la captura automática de descarga del navegador no pudo confirmarse |
| Integración | Telemetría validada recibida; MOSTO válido y 18 °C aplicados en las verificaciones; SQLite `integrity_check=ok`; Grafana con base saludable |

La prueba de interfaz creó una receta llamada **VALIDACIÓN DE INTERFAZ · no usar para elaborar**, con dos versiones, y un lote **VALIDACIÓN UI · banco sin compresor**. La densidad ficticia se identificó como tal en instrumento y observaciones. OG 1.050, SG 1.020 y FG estimada 1.010 dieron 60 % de atenuación aparente y 75 % de avance hacia FG. Estos valores prueban formularios/cálculos, no una fermentación.

La receta quedó archivada y el lote cancelado, sin borrar el historial ni dejar un lote activo. No se crearon lotes clasificados como reales ni se escribieron esas densidades en InfluxDB. El perfil antiguo de prueba no fue reemplazado.

## Límites y próximos pasos

No se verificó una fermentación real, estabilidad medida durante días, refrigeración con compresor, autenticación de operadores, pantalla móvil ni restauración completa de la infraestructura. Los tests con reloj controlado no equivalen a esos ensayos.

Grafana conserva el histórico térmico y la supervisión física; todavía no etiqueta retrospectivamente sus series por lote ni compara fermentaciones reales. El servicio nuevo clasifica sus propios lotes, sin atribuirles automáticamente datos anteriores. No se implementó ML ni autorización de consignas remotas.

La plantilla de Actions continúa inactiva por el permiso `workflow` faltante; se amplió como ejemplo con los nuevos tests. No se declara una ejecución de CI.

Ver [manual, arquitectura y recuperación](../server/profiles/README.md).
