# Validación de hardware — baseline determinista

**Estado: pendiente.** No marcar aceptada esta etapa solamente porque compila o pasan pruebas host. Registrar resultados por fase, firmware/commit, entorno, ROM, módulo de relé, montaje y evidencias Serial/medición física. Ninguna fase habilita perfiles completos ni lógica adaptativa.

## Conectar el montaje actual

Hacer el cableado sin alimentación. Compresor desconectado en A–C. Para sondas DS18B20 ya preparadas:

| Conductor identificado de cada sonda | ESP32 |
|---|---|
| VDD / alimentación | 3V3 |
| GND | GND |
| DATA / DQ | GPIO 4 (compartido) |

Usar alimentación de tres hilos. Pull-up 4,7 kΩ entre DATA y 3V3; si el conjunto ya la tiene, verificar a qué tensión está conectada y no agregar otra a ciegas. Dos resistencias iguales en paralelo equivalen a 2,35 kΩ: registrar el montaje y evaluar forma de onda/lecturas si hay errores. Colores de sondas no son universales; verificar identificación del proveedor o cableado existente. La resistencia de DATA nunca va a 5 V en este montaje.

Módulo doble con `GND`, `IN1`, `IN2`, `VCC`:

- El canal usado por el código es `IN1` conectado a GPIO 26 **solo si su entrada admite control de 3,3 V y no devuelve 5 V al ESP32**.
- `GND` debe compartir referencia con ESP32 para esta interfaz directa.
- `VCC` depende del módulo: identificar tensión nominal y circuito antes de alimentarlo. No decidirla únicamente por los nombres de los pines ni conectar una bobina directamente al ESP32.
- IN2 no tiene un canal en este firmware. Mantener el segundo canal sin carga; aplicar su estado inactivo según el módulo identificado, evitando una entrada flotante.
- COM/NO/NC permanecen sin compresor ni tensión de red en A–C.

Registrar etiqueta de bobinas y modelo de placa; confirmar ACTIVE LOW y que HIGH=3,3 V realmente apaga el canal. Un módulo alimentado a 5 V puede necesitar interfaz adecuada. Antes de conectar el compresor verificar OFF con ESP32 reseteado, sin alimentación y durante carga de firmware. El GPIO queda de alta impedancia antes de `setup()`: el firmware no sustituye la polarización externa a un nivel seguro compatible. Medir primero, sin cargas de red.


### Módulo mostrado: SRD-05VDC y jumper JD-VCC/VCC

La imagen aportada muestra bobinas de 5 V, optoacopladores y ese jumper. Para el circuito habitual de esta familia, separar alimentaciones quitando el jumper: VCC lógica a 3,3 V; JD-VCC bobinas a 5 V regulados; GND común; IN1 a GPIO 26; IN2 al nivel inactivo 3,3 V. Agregar pull-up de 10 kΩ desde IN1/GPIO 26 a 3,3 V para sostener OFF durante reset, después de confirmar compatibilidad. El modelo exacto de placa no está identificado: confirmar que VCC y JD-VCC estén separados sin jumper y probar polaridad/activación con 3,3 V sin carga. Si la activación es insuficiente, detener y usar una interfaz verificada, sin elevar VCC/IN directamente a 5 V con ESP32 conectado.

No tomar VIN como una salida de 5 V sin identificar la placa y medirlo. Mantener todos los bornes de contactos sin tensión de red en estas pruebas. Referencia de la topología: [fabricante, lógica y bobinas separadas](https://forum.sunfounder.com/t/usage-of-jumper-and-12v-on-sunfounder-5v-8-channel-relay/1426); es una referencia de familia y no certifica este clon.

## Preparación y evidencia

1. Identificar puerto USB y cerrar otros monitores. Alimentar primero solo ESP32 por USB.
2. Compilar con `secrets.ini` privado o de demostración; no copiar credenciales a logs públicos.
3. Registrar commit y entorno. DRY_RUN y HARDWARE son firmwares distintos; el modo aparece en BOOT y telemetría.
4. Verificar que Node-RED no esté ejecutando perfiles para estas pruebas. Los entornos físicos deshabilitan comandos MQTT y OTA; no modificar servicios como parte de esta guía sin plan explícito.
5. Conservar tiempo monotónico de eventos. Para medir OFF del GPIO/contactos usar instrumental; un log no prueba la salida eléctrica.

## FASE A — sin relé ni sensores

1. Ejecutar `scripts/test_host.sh`: guard, casos A–P, JSON y pruebas previas deben pasar.
2. Compilar `esp32-dry-run` y `esp32doit-devkit-v1`. No cargar HARDWARE todavía.
3. Cargar DRY_RUN: `pio run -e esp32-dry-run -t upload --upload-port PUERTO`.
4. Abrir Serial a 115200. Esperar BOOT con `mode=DRY_RUN`, `relay=OFF`, hold=300s. Sin sensores aparecerá SENSOR_FAULT; no hay refrigeración autorizada.
5. Enviar `SIM MOSTO 25`, `SIM AMBIENTE 22`, `SP 18`, `HYST 0.3`, `MAINT OFF`.
6. Tras tres muestras, STATUS debe mostrar MOSTO y AMBIENTE válidos, BOOT_HOLD y `relay=0` antes de uptime 300 s. La simulación no acorta la espera.
7. Al alcanzar 300 s debe aparecer COOLING, request/active=1, **relay=0**. Medir GPIO 26: nunca LOW en DRY_RUN.
8. Enviar `SIM MOSTO 17.6`: IDLE, active=0. Volver a `SIM MOSTO 25`: COMPRESSOR_LOCKOUT por 300 s desde el apagado.
9. Enviar `SP 30`, `SP nan`, `SP 18basura`: rechazo y aplicado anterior intacto. `SP 19` debe aplicarse. `HYST 0` se rechaza.
10. `MAINT ON`: OFF lógico. `MAINT OFF`: recuperar solo con sensores válidos y protección satisfecha.
11. `SIM MOSTO 85`, luego `SIM MOSTO OFF`: SENSOR_FAULT/OFF. Volver a `SIM MOSTO 25`: tres muestras para recuperar y ninguna elusión del guard. `SIM AMBIENTE OFF` solamente: control sigue y degraded=1.
12. Reiniciar estando en COOLING lógico: observar OFF y otros cinco minutos desde reboot.

Para probar MQTT usar `esp32-mqtt-test` y un broker controlado. Publicar manualmente `18`, `30`, `18basura`, payload vacío y `nan` en `birra/setpoint`; comprobar aceptación/rechazo. Detener broker/router: Serial sigue actualizando ciclos/control y mantiene SP aplicado. Restaurar: MQTT_RECOVERED, estado actual y contador de pérdidas. Si nunca hubo conexión, el contador de pérdidas puede ser cero: STATUS igualmente muestra mqtt=0.

## FASE B — sensores solamente

1. Mantener DRY_RUN y compresor/relé desconectados. Cablear ambas sondas como arriba.
2. Enviar `SIM CLEAR`, `ROM`. El diagnóstico fuerza MAINTENANCE y muestra ROM, temperatura y motivo. Una lectura de diagnóstico no habilita control.
3. Desconectar una sonda, repetir ROM y registrar cuál desaparece. Alternativamente calentar solo una sonda con la mano y observar. Asignar MOSTO/AMBIENTE en `include/hardware_config.h`; no usar índice.
4. Recompilar/cargar DRY_RUN con ese mapeo y enviar `MAINT OFF` si corresponde. Verificar tres conversiones válidas antes de habilitar MOSTO. Confirmar valores plausibles frente a una referencia.
5. Desconectar MOSTO durante ejecución: SENSOR_LOST, SENSOR_FAULT, request/active=0. La detección depende del siguiente intento de lectura; registrar latencia (objetivo normal <=2 s, control local aplica OFF en el ciclo que detecta la falla).
6. Reconectar MOSTO: tres lecturas válidas, FAULT_RECOVERED y guard vigente. Repetir desconexión/reconexión de AMBIENTE: degraded=1 y control de MOSTO continúa.
7. Confirmar que STATUS cambia con el servidor/router apagado. Una temperatura estable por sí sola no prueba un sensor bloqueado: comprobar presencia/lecturas CRC y frescura.

## FASE C — relé sin compresor

1. Identificar alimentación/compatibilidad del módulo y conexión GND/IN1/VCC. Mantener COM/NO/NC sin carga de red y canal 2 sin carga.
2. Con DRY_RUN, medir GPIO HIGH y verificar contacto del canal 1 en reposo. Si el relé se activa con HIGH o durante reset, detener y corregir interfaz/polarización.
3. Comprobar contacto y GPIO durante USB desconectado, botón reset, boot, carga de firmware y caída de alimentación. Debe permanecer inactivo. Registrar resultado físico.
4. Solo después de B y polaridad correcta cargar `esp32doit-devkit-v1` (HARDWARE), todavía sin compresor. Las simulaciones no existen en ese modo.
5. Usar MOSTO real y una consigna válida inferior a su temperatura para solicitar refrigeración. Verificar OFF durante los primeros 300 s aun con demanda alta.
6. Después del hold, medir GPIO LOW/contacto activo en COOLING. Cambiar consigna por Serial para que T<=SP-histéresis: comprobar OFF real.
7. Volver a solicitar: COMPRESSOR_LOCKOUT y contacto OFF durante cinco minutos desde ese apagado. Repetir con falla/reconexión de MOSTO, mantenimiento y reinicio.
8. Probar `SP 30`/`SP 18basura` y pérdida de red: no cambian indebidamente salida o consigna. Revisar `control_max_gap_ms` y ausencia de internal_error durante cambios NVS y reintentos MQTT.

## FASE D — refrigeración real

Solo después de aprobar A–C, interfaz/polarización OFF, características eléctricas del relé y montaje adecuado para el compresor. Conectar el equipo de refrigeración mediante la instalación correspondiente; esta guía no define cableado de tensión de red.

1. Registrar volumen y disposición de sonda MOSTO; usar agua para caracterizar respuesta, sin automatizar perfiles. Confirmar refrigeración únicamente, sin calefacción.
2. Ejecutar SP fijo y banda configurada. Medir T>SP+h para inicio y T<=SP-h para corte, junto con el contacto real. No saltar protección para acelerar ensayos.
3. Observar varios ciclos y al menos un intervalo completo de apagado de 300 s. Registrar temperaturas, estados y tiempos.
4. Reiniciar mientras debería refrigerar: OFF físico inmediato al reset/montaje seguro y BOOT_HOLD completo después de reiniciar.
5. Apagar Wi-Fi/broker/servidor por separado: el control sigue local y conserva consigna; recuperar y comprobar contadores/telemetría.
6. Desconectar MOSTO: compresor OFF al detectar falla; reconexión exige tres muestras y guard. Desconectar solo AMBIENTE: continuar con degraded=1.
7. Ensayar mantenimiento, consigna inválida y carga sostenida de red controlada. Si hay watchdog/error interno, registrar causa; no aprobar sin investigar.

## Registro de aceptación

| Criterio | Estado inicial | Evidencia a registrar |
|---|---|---|
| Compila DRY_RUN / HARDWARE | Aprobado en software, 2026-10-06 | VALIDATION_RESULTS.md |
| Unit tests y JSON | Aprobado en host, 2026-10-06 | VALIDATION_RESULTS.md |
| Relé físicamente OFF en boot/reset/carga | Pendiente | Medición GPIO/contacto |
| Ningún inicio antes de 300 s | Pendiente | Uptime y contacto real |
| Falla MOSTO fuerza OFF | Pendiente | Desconexión, evento y contacto |
| AMBIENTE perdido permite control degradado | Pendiente | Serial y temperatura MOSTO |
| MQTT/Wi-Fi offline no detienen control | Pendiente | Ciclos/temperatura/salida sin red |
| Consigna inválida conserva aplicada | Pendiente | Payload y STATUS |
| Telemetría explica decisiones | Pendiente | JSON real y logs |
| Procedimiento reproducible | Esta guía | Resultado de A–D |

Actualizar con fecha, commit, resultado observado y archivo de evidencia. Un resultado simulado se marca como tal. Hasta completar los criterios físicos: **baseline implementada, etapa no aceptada**.
