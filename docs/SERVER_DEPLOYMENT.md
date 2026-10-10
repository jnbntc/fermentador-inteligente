# Supervisión del servidor: despliegue del 10 de octubre de 2026

Esta entrega mejora Node-RED y Grafana con autorización del propietario. No cambia firmware, protección de arranque, control del relé, OTA ni decisiones de fermentación. **Ensayo de banco sin compresor; refrigeración real pendiente: FASE D.** Los perfiles y recetas siguen siendo de prueba.

## Node-RED

- Node-RED 3.1.9 / Node.js 16.20.2; 38 nodos originales y 10 nuevos, organizados en cuatro grupos.
- Contrato de telemetría validado antes del almacenamiento; temperaturas inválidas se omiten conservando flags y fallas.
- Progreso y `estado_lote` coherentes en el store `file`, guardados antes de retornar ante un cambio de consigna.
- Consignas calculada/aplicada separadas; inicio repetido rechazado; vigencia periódica desde el arranque; Catch/Status de diagnóstico.
- Bloqueados el publicador de consignas MQTT, Telegram, inicio de lote y trigger de vigencia antiguo.
- Pestaña Clima, configuraciones compartidas y archivo de credenciales cifradas conservados.
- Despliegue por API v2 con revisión concurrente; runtime y disco coinciden. Backup privado completo del directorio activo antes de desplegar; pausa de Node-RED de 15,05 segundos durante la copia.

SHA-256 de flujos originales: `b28c7fd88613e41f1bd4567cfa3992a0e7cd1d2e27c96b5c6f81858f653b11d6`.

SHA-256 de flujos del primer despliegue: `42418d4ce151eca9248c8c3825410378c9040c301e2fe2e29277e0d222df0066`.

El respaldo privado de Node-RED se identifica por `nodered-20261010T131154Z`; su archivo tiene SHA-256 `58979ecc4e2ac694bf6820b838ed09e5a035d0fbd9db6165372b85587e6ae080`.

Se comprobaron recepción de dos mensajes reales consecutivos, avance de uptime/ciclos, ambas sondas válidas, escritura y lectura en InfluxDB, contexto persistente y Dashboard 2 mostrando 3 °C calculados frente a 18 °C aplicados. La consigna de prueba no se publicó al dispositivo.

Después del primer despliegue se observaron cambios del usuario en posiciones del editor y en la plantilla de una receta futura (18/20/3/2 °C). Se conservaron; los cuatro bloqueos permanecen activos. El perfil activo persistido sigue siendo el de prueba anterior: editar la plantilla no reinicia ni reemplaza el lote guardado.

El estado actual también quedó respaldado como `nodered-20261010T134622Z`, con 48 nodos, integridad verificada y pausa de 7,38 segundos. SHA-256 del archivo: `d5ff504e92efd6750d7827ce550cee6ddf7781405c16dce0cf83fd1c6ebb0258`. El archivo de flujos observado después de esos ajustes tiene SHA-256 `6c550fd7f61aa44a30f300cd28ff09207300be373d0bab89855d66d83bc4c021`.

Las referencias saneadas del repositorio reproducen el primer parche y sus pruebas; no son una exportación completa del estado activo posterior ni un mecanismo para sobrescribir los ajustes del usuario.

## Grafana

Grafana permanece en 10.4.2. Se reemplazó el recurso `kind/spec` de Grafana 13 por un dashboard clásico compatible. El error periódico «Dashboard title cannot be empty» desapareció. El dashboard mantiene UID, título y datasource existentes; conserva los IDs de los tres paneles anteriores y agrega supervisión de estado, vigencia, sensores y diagnóstico.

El progreso ya no usa la primera medición histórica como fecha de inicio. Se consulta `estado_orquestador`, etiquetado como perfil de prueba. El desvío usa MOSTO y consigna aplicada del mismo timestamp. Los valores vencidos no se muestran como actuales. La cabecera declara el ensayo de banco y FASE D pendiente.

Se agregó únicamente a Grafana el volumen persistente de provisioning, de solo lectura. Se recreó solo ese servicio, conservando imagen, datos, usuarios y datasource. Los contenedores MQTT, Node-RED e InfluxDB conservaron sus IDs y los flujos de Node-RED no cambiaron durante esta operación. No se modificaron los parámetros de autenticación.

El respaldo privado de Grafana, `grafana-20261010T132512Z`, contiene datos, configuración, provisioning original, Compose y metadata de recuperación. Directorio 0700; archivo 0600, 24.114.698 bytes. Se comprobó `PRAGMA integrity_check = ok` y el hash del SQLite dentro del archivo. La pausa durante la copia duró 0,23 segundos. SHA-256 del archivo: `0973607d0b17e8c84ea57913007b517ca3c5a5dcaeaeaa3950b7a6adbbc4128c`.

Ambos respaldos permanecen exclusivamente en el servidor, bajo `$HOME/.local/state/fermentador/backups/`. No se publicó su contenido, credenciales, sesiones, direcciones privadas ni SSID. No se ensayó una restauración completa ni se necesitó rollback.

## Comprobaciones y alcance

| Comprobación | Resultado y límite |
|---|---|
| Funciones Node-RED | 20 casos en Node.js 16.20.2 y 24.19.0, aislados; incluyen regresiones del flujo original |
| Formato/generador Grafana | Seis tests locales de contrato y reproducibilidad; no sustituyen el render |
| Consultas Flux | 30 HTTP 200: diez consultas en rango real, vacío y cierre futuro para evaluar antigüedad; se verificaron filas y ausencia de valores artificiales |
| MQTT → InfluxDB | Nuevas muestras reales del equipo de banco, con validez, consigna, relé, ciclos y progreso |
| Dashboard Node-RED | Consignas calculada y aplicada separadas |
| Grafana | Salud y base de datos correctas; diez paneles aprovisionados y lectura a través de su datasource existente; cero errores de Grafana en la ventana revisada tras el despliegue |
| Interfaz | Gráficos, tablas, unidades y estado textual comprobados en navegador; intervalo de 15 minutos y retorno al de seis horas. No se comprobó una pantalla móvil |
| Física | No se conectó compresor ni se ejecutó una nueva aceptación de refrigeración |

Las consultas de verificación fueron de lectura. Las pruebas aisladas usan contexto simulado; no escriben lecturas en MQTT o InfluxDB. La evaluación de datos vencidos usa un cierre de intervalo futuro, sin desconectar el dispositivo ni cambiar su reloj. La continuidad offline y las fallas de sondas de las pruebas físicas anteriores no se atribuyen a este nuevo despliegue.

## Operación y recuperación

- [Node-RED: funciones, referencias y bloqueos](../server/nodered/README.md).
- [Grafana: consultas, vigencia, respaldo, migración y recuperación](../server/grafana/README.md).
- Las funciones aisladas y el contrato del dashboard se comprobaron durante esta entrega. `server/ci/server-workflow.yml.example` conserva una plantilla para Actions, sin activar: la autorización disponible de GitHub no permite escribir workflows. No se declara una ejecución de CI que no ocurrió; la plantilla no accede al servidor ni usa secretos.
- Para restaurar se necesita el respaldo privado y su configuración de recuperación; detener solamente el servicio afectado y conservar antes cualquier cambio posterior. No restaurar SQLite mientras Grafana escribe.

Quedan pendientes la refrigeración real, identificación de lotes/datos de banco en el almacenamiento, densidad manual y atenuación integradas, políticas operativas de alarma y actualización segura de versiones. La biblioteca de recetas Python aún no está conectada a Node-RED. No se implementó aprendizaje automático.
