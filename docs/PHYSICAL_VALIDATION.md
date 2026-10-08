# Pruebas físicas con salida simulada: DRY_RUN

Evidencia aportada por el usuario el 2026-10-06. La operación se realizó desde iot-dev, con PlatformIO 6.1.18 y /dev/ttyUSB0. No es una medición directa del agente.

## Confirmado por la salida Serial

- Compilación/carga esp32-dry-run: SUCCESS, 16,529 s.
- BOOT: mode=DRY_RUN, relay=OFF, boot_hold=300s, remote_setpoints=0, OTA=0.
- Dos ROM encontradas y coincidentes con el mapeo existente:
  - MOSTO: 28:FF:B0:96:51:16:04:18.
  - AMBIENTE: 28:FF:6A:47:55:16:03:68.
- Primer diagnóstico: ambas 85,00 °C, reason=power_on_85. No se autoriza control con esa lectura.
- Después: MOSTO 20,88 °C; segundo diagnóstico AMBIENTE 20,50 °C.
- SENSOR_FAULT inicial -> BOOT_HOLD, FAULT_RECOVERED y SENSOR_AVAILABLE para ambas sondas. La demanda de refrigeración aparece sin un evento de inicio en el fragmento recibido.
- Se muestran dos arranques. La secuencia es compatible con carga y reset manual solicitado; no se presenta como un reinicio espontáneo.

## Mensajes a interpretar

Preferences nvs_open NOT_FOUND corresponde a un namespace nuevo sin configuración guardada. El código conserva los valores iniciales; aún no se verificó la persistencia con SP válido y reinicio.

COMMAND_REJECTED indica una línea que no coincide con los comandos admitidos. El fragmento no contiene el texto enviado: no se puede atribuir la causa a minúsculas, espacios o configuración del monitor.

## Pendiente

- Medir latencia de detección y registrar el intervalo inicial completo; la primera muestra COOLING recibida es posterior a 300 s y no mide el instante exacto del inicio.
- Comparar temperaturas con referencia y repetir pérdida aislada de AMBIENTE sin afectar MOSTO.
- Medir GPIO/contacto real; el log relay=OFF no prueba el nivel eléctrico.
- Pérdida/restauración de una conexión previamente establecida, consignas inválidas, persistencia y fases C/D.

La etapa sigue sin aceptación física completa.

## Secuencia posterior aportada por el usuario

Todos los estados siguientes pertenecen a DRY_RUN. `active=1` describe enfriamiento lógico simulado; `relay=0` es el estado informado por firmware, sin medición eléctrica independiente.

| Uptime (s) | Estado | MOSTO (°C / válida) | AMBIENTE (°C / válida) | Active / relay | Bloqueo (s) | Observación |
|---|---|---|---|---|---|---|
| 310 | COOLING | 20,625 / sí | 20,250 / sí | 1 / 0 | 0 | Demanda con SP 18 y banda 0,3 |
| 479 | COOLING | 20,750 / sí | 31,750 / sí | 1 / 0 | 0 | Calentar una sonda elevó AMBIENTE; permite identificar esa sonda física |
| 737 | SENSOR_FAULT | nan / no | nan / no | 0 / 0 | 235 | Usuario confirma desconexión accidental de ambas |
| 794 | SENSOR_FAULT | -127 / no | 24,625 / sí | 0 / 0 | 178 | Reconectó solo AMBIENTE; MOSTO ausente mantiene falla |
| 873 | COMPRESSOR_LOCKOUT | 22,000 / sí | 24,000 / sí | 0 / 0 | 99 | Recuperación de MOSTO respeta bloqueo; evento previo remaining=112 |
| 1144 | COMPRESSOR_LOCKOUT | 22,125 / sí | -127 / no | 0 / 0 | 273 | AMBIENTE ausente y degraded=1, fault=none |
| 1533 | COOLING | 22,375 / sí | -127 / no | 1 / 0 | 0 | Control degradado después del bloqueo |
| 1700 | COOLING | 22,375 / sí | -127 / no | 1 / 0 | 0 | Sigue controlando con MOSTO válida, degraded=1, fault=none |

Antes de la muestra de uptime 1144 aparece otra recuperación SENSOR_FAULT -> COMPRESSOR_LOCKOUT con remaining=297. MOSTO perdió validez también durante esa maniobra; no se acredita una desconexión exclusivamente de AMBIENTE sin perturbaciones. La causa no está determinada. Sí se observa funcionamiento posterior con MOSTO válida y AMBIENTE sostenidamente ausente, incluyendo COMPRESSOR_START mode=DRY_RUN physical_relay=0.

Las muestras muestran wifi=0 y mqtt=0, SP aplicado 18 °C, ciclos que avanzan y max_gap_ms=29. Acreditan funcionamiento mientras no hay conexión; no prueban pérdida/restauración de un transporte previamente conectado, ni un ensayo de dos horas.

Se repiten líneas con caracteres de reemplazo (ilegibles), intercaladas con STATUS completos. No se atribuyen al sensor, a baud rate ni a un error de memoria sin evidencia. Se debe capturar una sesión limpia del monitor y resolver esta limitación de observabilidad antes de dar por aceptado el montaje.

## Consignas inválidas y restauración de AMBIENTE

AMBIENTE se reconecta: a uptime 1984, MOSTO 22,375 y AMBIENTE 22,125, ambas válidas, degraded=0 y fault=none. Reaparece COMPRESSOR_LOCKOUT con 235 s antes de enviar SP 30. No se aportaron los eventos completos de esa reconexión: no se atribuye ese apagado al comando posterior ni se confirma su causa.

- SP 30: SETPOINT_RECEIVED seguido de SETPOINT_REJECTED range; applied=18.000.
- SP nan: SETPOINT_REJECTED invalid payload; applied=18.000. La primera respuesta contiene un prefijo ilegible; la repetición siguiente es legible.
- SP 18basura: SETPOINT_REJECTED invalid payload; applied=18.000.
- STATUS a uptime 2124: desired=30.000 (solicitud finita rechazada), applied=18.000, hyst=0.300, ambas sondas válidas, degraded=0, fault=none, COMPRESSOR_LOCKOUT con 96 s, active=0 y relay=0.

La reapertura del monitor no eliminó las líneas ilegibles intermitentes. Se preparó una captura con PySerial fuera del monitor de PlatformIO, de bytes originales y tiempos, que envía únicamente STATUS. No se modifica el firmware para intentar corregir una causa no identificada.

## Captura directa de UART

El usuario ejecutó la captura de 30 s desde iot-dev. Archivos locales de evidencia: outputs/capturas-serial/20261007T002625.907922Z.bin y el JSONL del mismo nombre (fecha UTC; corresponde a la noche del 2026-10-06 en Buenos Aires). El agente leyó ambos archivos y comprobó que la concatenación de los bloques hexadecimales del JSONL coincide exactamente con el binario: 2299 bytes, cero bytes >=128 y seis respuestas STATUS. Último bloque recibido a 26,152 s.

La apertura estuvo acompañada por un reinicio: BOOT mode=DRY_RUN reset_reason=1, relay=OFF, hold=300s. Ambas ROM están presentes. A 3,1 s de captura se registra recuperación de MOSTO y AMBIENTE; los STATUS posteriores muestran BOOT_HOLD, request=1, active=0, relay=0, fault=none y bloqueo descendente de 295 a 275 s. El gap máximo observado es 25 ms. El mensaje NVS NOT_FOUND continúa: aún no se ensayó una escritura válida/persistencia.

Esta muestra es limpia. No demuestra que el fallo esté resuelto ni que sea exclusivo del monitor de PlatformIO: es más breve y envía comandos cada 5 s. Falta comparar una captura con intervalos de silencio más largos y/o reproducir el fallo con bytes originales antes de atribuir una causa.

### Capturas con consultas cada 20 segundos

Tras solicitar una ejecución de 120 s y STATUS cada 20 s, el usuario informa que terminó sin caracteres raros. Se encontraron dos nuevos pares de archivos, 20261007T002835.386902Z y 20261007T003044.838301Z. En ambos, el agente verificó equivalencia exacta BIN/JSONL, 2304 bytes, cero bytes >=128 y seis respuestas STATUS; últimos datos a 101,304 y 101,294 s respectivamente (la captura permanece esperando entre consultas).

Ambas sesiones incluyen un arranque y terminan con BOOT_HOLD a uptime 100, lockout=200, ambas sondas válidas, degraded=0, fault=none, active=0, relay=0 y max_gap_ms=28. Las capturas directas siguen sin reproducir la corrupción. La causa de las líneas ilegibles del monitor permanece pendiente; estas muestras no prueban ausencia de fallas fuera de las ventanas registradas.

## Persistencia de consigna y nueva reproducción en PlatformIO

El usuario envió SP 19: SETPOINT_RECEIVED y STATUS posterior con desired=applied=19.000. Durante la primera escritura aparecen errores getBytesLength setpoint/hysteresis NOT_FOUND: la librería intenta leer esas claves aún inexistentes antes de guardarlas. No hay CONFIG_ERROR y los reinicios posteriores recuperan SP 19. No se infiere un fallo de escritura de esos mensajes iniciales.

Después del reset se observan dos bloques de arranque reset_reason=1, sin evidencia que permita explicar por qué fueron dos. El arranque recupera SP=19 y aplica BOOT_HOLD. A uptime 23, MOSTO 22,250 y AMBIENTE 26,125, ambas válidas; desired=applied=19.000, fault=none, active=0, relay=0, lockout=277 y max_gap_ms=26. Se acredita persistencia de la consigna mediante los logs aportados, sin lectura independiente de NVS.

En esa sesión de PlatformIO vuelve a aparecer un prefijo ilegible en una respuesta STATUS; la siguiente es legible. También un STATUS visible en consola resulta COMMAND_REJECTED. La consola no prueba los bytes transmitidos. Se preparó instrumentación del mismo monitor para guardar RX antes de su decodificador y TX después de escribir al puerto. No cambia baud rate, filtros ni señales de control del monitor; todavía falta ejecutar esa captura sobre la placa y restaurar SP a 18.

## Primera captura dentro de PlatformIO

El usuario aporta RESUMEN PIO: RX=1075, no ASCII=0, TX=39. El agente verifica que el archivo pio-20261007T003855.440199Z.bin coincide exactamente con los eventos RX del JSONL. TX contiene SP 18 seguido por cuatro STATUS; no hay respuesta de aceptación/rechazo del SP en esa captura. Los cuatro STATUS mantienen applied=desired=19.000: restauración a 18 todavía pendiente.

Se observa BOOT_HOLD a uptime 273 (bloqueo 27) y 299 (bloqueo 1), seguido de COOLING a 302 y 305; ambas sondas válidas, fault=none, degraded=0, relay=0 y max_gap_ms=29. Es evidencia del hold lógico alrededor del umbral de 300 s, sin medición eléctrica de GPIO/contactos.

Una captura inmediatamente anterior, pio-20261007T003822.869606Z, tiene RX=0 y TX=13. Los bytes transmitidos son `P\x08\x08\x08SP 18\r\n\r\n`: el filtro send_on_enter original envía los retrocesos como datos. Esa secuencia no coincide con un comando válido del parser, aunque falta la respuesta RX para acreditar qué ocurrió en ese intento. Este hallazgo no explica los prefijos no ASCII de respuestas anteriores.

El lanzador local del monitor se ajustó para que Backspace/Delete editen el buffer antes de transmitir y Ctrl+U borre la línea. No se modifica la librería instalada ni el firmware; se conserva la captura RX/TX. Prueba con puerto virtual: la secuencia `P` con retrocesos y corrección de `SP 19` a `SP 18` transmite exactamente `SP 18\r\n`, y una respuesta con 64 bytes FF queda intacta en el archivo RX. Aún no se probó esa corrección de teclado en la placa.

## Restauración de la consigna de prueba

Tras reabrir el monitor, el usuario aporta SETPOINT_RECEIVED source=SERIAL value=18.000 y un STATUS a uptime 535: COOLING, MOSTO 22,250, AMBIENTE 22,625, ambas válidas, desired=applied=18.000, hyst=0.300, request=active=1, relay=0, lockout=0, degraded=0, fault=none y max_gap_ms=29. La restauración de la consigna aplicada está confirmada por Serial. No se realizó un nuevo reinicio para verificar independientemente la persistencia de 18 ni se ensayó la edición mediante retroceso en esta interacción.

## Mantenimiento y cambios de consigna

El usuario envía MAINT ON desde COOLING: eventos MAINTENANCE enabled, COOLING -> MAINTENANCE, COOLING_REQUEST off y COMPRESSOR_STOP mode=DRY_RUN physical_relay=0. STATUS a uptime 616: MAINTENANCE, request=active=0, relay=0, lockout=288, SP aplicado 18, ambas sondas válidas y fault=none.

MAINT OFF produce COMPRESSOR_LOCKOUT remaining=282 y demanda de frío. STATUS a uptime 630: request=1, active=relay=0, lockout=274. Salir de mantenimiento no elude ni reinicia el intervalo de protección.

Mientras ese bloqueo sigue vigente, SP 24 produce IDLE y COOLING_REQUEST off. STATUS a uptime 711: MOSTO 22,250, ambas sondas válidas, desired=applied=24.000, request=active=relay=0, lockout=193 y fault=none. Después SP 18 produce COMPRESSOR_LOCKOUT remaining=182 y COOLING_REQUEST on. STATUS a uptime 732: desired=applied=18.000, request=1, active=relay=0, lockout=172 y fault=none; max_gap_ms=29 en ambos estados. Se comprueba cambio de demanda por consigna y que IDLE no extiende un intervalo OFF ya existente. No se mide aquí el corte normal desde COOLING por alcanzar la temperatura ni los umbrales exactos de histéresis.

El comando mal escrito SYATSY se rechaza; el STATUS posterior funciona. Los fragmentos de estas pruebas son legibles, pero no se marca resuelta la corrupción intermitente anterior.

Pendiente antes de la fase eléctrica: respuesta del usuario sobre disponibilidad de multímetro y cableado actual del módulo (VCC, JD-VCC, GND, IN1, IN2 y jumper). Mantener compresor desconectado y DRY_RUN hasta verificar esa interfaz.

### Cableado comunicado antes de la medición

El usuario informa GND -> GND, JD-VCC sin cable, VCC -> 3 V, IN1 -> GPIO 26 e IN2 -> VIN. Tiene un multímetro, pendiente localizarlo. No confirma todavía estado del jumper ni fuente externa de 5 V. Se indica cortar alimentación antes de cambiar conexiones, retirar IN2 de VIN y usar el nivel inactivo referido a VCC lógica/3V3 del montaje previsto. Mantener JD-VCC sin alimentar hasta identificar el puente y verificar interfaz. Si el jumper une VCC y JD-VCC, no hay separación eléctrica aunque JD-VCC no tenga cable independiente. No hay mediciones de voltaje, continuidad, polaridad ni contactos registradas todavía.

### Primeras mediciones de tensión

Después de indicar jumper retirado, IN2 unido a VCC lógica y JD-VCC sin alimentar, el usuario comunica mediciones con multímetro: VIN=5 V, 3V3=3,3 V y GPIO 26=3,3 V. Es evidencia aportada por el usuario del nivel HIGH en régimen DRY_RUN, sin captura directa del instrumental. Aún no se verifica eléctricamente OFF durante reset/carga, ni estado de contactos con las bobinas alimentadas. La medición en vacío de VIN no caracteriza la capacidad de corriente ni su caída bajo carga; se debe comprobar tensión al alimentar el módulo. No se cargó HARDWARE ni se conectó el compresor.

Después de indicar separación VCC/JD-VCC, conexión VIN -> JD-VCC y medición con el módulo alimentado, el usuario responde que midió los valores previstos: JD-VCC aproximadamente 5 V, VCC y GPIO 26 aproximadamente 3,3 V. No aporta todavía resultado explícito de continuidad VCC/JD-VCC, estado de indicador/clic ni mediciones COM/NC/NO. No se acredita activación/polaridad de contactos ni capacidad de alimentación con bobina activada; la siguiente comprobación es reposo de contactos del canal IN1, libres de cables y tensión externa.

### Contactos del canal IN1 en reposo

Foto real aportada: bornes abajo, R2 a la izquierda y R1 a la derecha. Los esquemas impresos muestran, de izquierda a derecha en cada grupo, NO/COM/NC. Numerando los seis tornillos desde la izquierda: R1 corresponde a 4=NO, 5=COM, 6=NC. Se indicó medir con USB conectado, DRY_RUN y todos los contactos libres de cables externos.

El usuario confirma continuidad 5/6 (COM/NC) y ausencia de continuidad 4/5 (NO/COM). Junto con GPIO 26=3,3 V y alimentación del módulo, acredita reposo del contacto del canal IN1 bajo esas condiciones. Todavía no demuestra activación con LOW, ni OFF durante reset, reconexión USB o carga. La siguiente prueba mantiene las puntas en 4/5 y observa si aparece continuidad al mantener y soltar EN/RESET; el multímetro no caracteriza pulsos más breves que su tiempo de respuesta.

### Reset y reconexión USB

Después de indicar medición NO/COM durante EN/RESET y desconexión/reconexión USB, el usuario responde que no pitó. Se registra ausencia de cierre observable con su multímetro en las pruebas solicitadas; no hay oscilograma ni medición de pulsos breves, y la respuesta no desglosa cada maniobra. No se presenta como una garantía frente a todos los transitorios.

La consola muestra Disconnected Input/output error y luego no encuentra ttyUSB0. Al inspeccionar sysfs, el agente verifica CP2102 VID=10c4/PID=ea60, runtime active, ahora enumerado como ttyUSB1. El entorno del agente sigue sin tener nodos /dev/ttyUSB accesibles, aunque sysfs identifica el adaptador. Se adapta el lanzador local para detectar un único CP2102 y preferir un alias by-id, manteniendo la opción de puerto explícito; no se cambian permisos ni servicios.

En el fragmento previo a desconectar aparece otro prefijo ilegible en una transición hacia COOLING. Las capturas PIO más recientes tienen RX=0 y no contienen ese evento: no se identifican todavía sus bytes originales ni la causa. COMPRESSOR_START sigue mode=DRY_RUN physical_relay=0. Todavía no se cargó HARDWARE.

### Arranque posterior y datos anómalos capturados

Tras otro reset, el usuario aporta un BOOT DRY_RUN con SP recuperado 18. El STATUS a uptime 18 muestra BOOT_HOLD, ambas sondas válidas, MOSTO 22,125 y AMBIENTE 23,250, request=1, active=relay=0, lockout=282, fault=none y max_gap_ms=26. Se acredita persistencia de 18 en ese reinicio. El prefijo del texto ROM está deformado; el texto pegado no basta para contar reinicios.

Al revisar las capturas pio-20261007T012157.267368Z y pio-20261007T012219.497412Z aparecen bytes no ASCII antes de la decodificación del monitor, con patrones repetidos y volumen anómalo. La primera contiene 4582417 bytes RX registrados en 4,179 s (BIN/JSONL coinciden); esto no es una secuencia normal de STATUS y no se atribuye al firmware sin investigar la instrumentación, configuración y transporte. La segunda estaba variando durante la lectura y no se usa para una comparación final exacta. No se acredita una causa ni resolución.

Se limita la captura a 128 KiB RX y se deshabilita reconexión automática tras error para evitar archivos sin límite durante un flujo anómalo. DTR/RTS del lanzador se fijan a 0 como en el lector directo de las capturas limpias. Es una prueba de configuración pendiente de repetir sobre la placa. Se prepara cargar-hardware-prueba.sh para la siguiente fase; no se ejecuta todavía mientras se verifica el monitor. No se modifica firmware ni se conecta el compresor.

### Sesión con DTR/RTS desactivados

El usuario reabre el monitor: consola forcing DTR inactive, forcing RTS inactive, alias persistente CP2102 by-id, 115200 8N1. Aporta un arranque legible DRY_RUN y un STATUS a uptime 67: BOOT_HOLD, ambas sondas válidas, MOSTO 22,125 y AMBIENTE 23,250, desired=applied=18.000, request=1, active=relay=0, lockout=233, fault=none y max_gap_ms=28. No aporta todavía RESUMEN de cierre. La muestra es legible con esa configuración; no establece causalidad ni resolución definitiva de la corrupción intermitente.

La siguiente prueba prevista es cargar HARDWARE con los bornes libres y compresor desconectado, observar OFF durante la carga/boot/hold y medir GPIO y contactos después de 300 s. Se conserva el monitor instrumentado y la limitación de captura. No se adelanta el guard ni se habilitan MQTT/OTA; la carga aún no está confirmada.

## Primera ejecución HARDWARE

Después de indicar cargar-hardware-prueba.sh, el usuario aporta STATUS a uptime 286: BOOT_HOLD, request=1, active=relay=0, lockout=14, SP 18, ambas sondas válidas, fault=none y max_gap_ms=29. Luego aparecen BOOT_HOLD -> COOLING y COMPRESSOR_START mode=HARDWARE physical_relay=1. STATUS a uptime 308 confirma COOLING, MOSTO 22,250 y AMBIENTE 23,250, ambas válidas, request=active=relay=1, lockout=0, fault=none y max_gap_ms=29. Wi-Fi/MQTT permanecen en 0.

El usuario informa que ahora prendió IN1. Esto confirma un indicador/activación observable del canal después del hold; todavía no aporta mediciones GPIO LOW, continuidad NO/COM con el canal activado ni tensión JD-VCC bajo esa condición. Tampoco aportó el bloque BOOT ni el resumen de carga en esta respuesta: la identificación HARDWARE se obtiene del evento COMPRESSOR_START. El compresor permanece desconectado según el montaje acordado; no se ensayó refrigeración real.

### Apagado inesperado al medir JD-VCC

El usuario informa que IN1 se apagó al medir JD-VCC. No comunica todavía posición del selector, conectores de puntas, valor mostrado, contacto accidental entre pines ni logs de ese instante. Se indica desconectar USB y pausar las pruebas físicas hasta verificar instrumento y cableado. No se atribuye el apagado a una protección correcta del firmware ni a un cortocircuito sin más evidencia.

El agente revisa los registros completos disponibles de pio-20261007T013422.882360Z: BOOT confirma HARDWARE, relay=OFF, hold=300s, remote_setpoints=0, OTA=0; muestras a uptime 38, 47, 266 y 286 permanecen en BOOT_HOLD y relay=0. A 308 se observa COOLING y relay=1. El archivo también tiene bytes no ASCII registrados (1632 en 10201 bytes RX de los bloques legibles al inspeccionar); el ajuste DTR/RTS no se considera solución definitiva del problema intermitente. No hay un evento posterior legible de apagado en los datos leídos. Tras pedir desconexión, sysfs no muestra ttyUSB: esto no determina la causa del apagado anterior.

La fase C permanece sin aceptación: falta aclarar el apagado durante la medición, verificar continuidad con bobina activada y completar corte/rearranque físico. No conectar compresor.

Posteriormente el usuario aporta otra carga HARDWARE fallida: The chip stopped responding, upload Error 2, duración 4,78 s. No se conoce el bloque completo anterior al error ni qué periféricos seguían conectados. No se concluye daño del ESP32 ni se continúa cargando firmware. Se indica aislar la placa de relé/sondas/display con USB desconectado y revisar el multímetro. Se prepara un diagnóstico de ROM con esptool 4.11.0, 115200, no-stub, tres intentos y read_mac: lectura de identificación sin borrar ni escribir flash, con los demás monitores cerrados. Falta ejecutarlo sobre la placa aislada. La guía oficial de Espressif contempla ruido serial, alimentación inestable, periféricos y puerto ocupado como posibles causas de fallos de comunicación/carga; ninguna se acredita todavía en este caso.

### Diagnóstico ROM con placa aislada

El usuario ejecuta diagnosticar-esp32.sh con placa sola por USB. Esptool 4.11.0 conecta a 115200 sin stub, identifica ESP32-D0WD-V3 revisión 3.1, cristal 40 MHz y lee la identificación MAC de ROM. Se omite la dirección única de este registro público. La operación termina Staying in bootloader: es el resultado previsto de --after no_reset, sin borrar ni escribir flash.

Esto acredita comunicación bidireccional y respuesta del cargador ROM en ese ensayo. No prueba integridad de todos los GPIO, alimentación bajo otras cargas, flash ni firmware después de la carga fallida. Se configura upload_speed=115200 en los entornos de PlatformIO y se actualiza cargar-dry-run.sh para detectar el puerto y usar el monitor instrumentado. La siguiente prueba es cargar/ejecutar DRY_RUN con la placa todavía aislada. Sigue pendiente revisar selector/conectores del multímetro antes de volver a medir o reconectar el relé.

### Ejecución DRY_RUN después del fallo

El usuario describe multímetro en V continua, escala 20, negro en COM y rojo en V/OMEGA/Hz: configuración adecuada para las mediciones de tensión propuestas. No aporta foto ni se conoce si esa misma configuración se mantuvo en el instante del apagado.

Después de ejecutar el cargador DRY_RUN con placa aislada, aporta un arranque legible: boot:0x13, BOOT mode=DRY_RUN reset_reason=1 relay=OFF hold=300s remote_setpoints=0 OTA=0, ROM found=0 y BOOT_HOLD -> SENSOR_FAULT mosto_sensor, SP 18. La ausencia de sondas explica el fallo de sensor. No aporta el resumen SUCCESS de carga, pero la ejecución de DRY_RUN después de HARDWARE acredita que puede volver a ejecutar ese firmware. No demuestra integridad de todos los GPIO ni del relé; la causa del apagado al medir JD-VCC sigue pendiente.

Se mantiene el relé y el resto de periféricos desconectados para medir 3V3, VIN y GPIO 26 en la placa sola. Preparar los puntos de medición con USB desconectado evita rozar pines vecinos al mover puntas. Todavía no se vuelve a alimentar el módulo ni se acepta la fase C.

### Tensiones de la placa aislada después de recuperar DRY_RUN

El usuario confirma los valores solicitados: 3V3 aproximadamente 3,3 V, VIN aproximadamente 5 V y GPIO 26 aproximadamente 3,3 V, con placa sola por USB. Estas lecturas acreditan alimentación y salida HIGH en reposo en esa condición; no caracterizan las bobinas bajo carga ni resuelven el apagado anterior.

Se propone reconectar únicamente la lógica del módulo, con USB desconectado durante el cableado: jumper VCC/JD-VCC retirado, GND común, VCC a 3V3, IN1 a GPIO 26 e IN2 a VCC del módulo. JD-VCC y VIN permanecen sin conexión al módulo; sondas y pantalla permanecen desconectadas. Después de alimentar por USB, comprobar VCC y GPIO 26 respecto de GND, ambos aproximadamente 3,3 V. Esta etapa aún está pendiente y mantiene DRY_RUN y los bornes libres, sin alimentar bobinas.

El usuario confirma la etapa de lógica: indicador IN apagado y ambas mediciones solicitadas aproximadamente 3,3 V. No informa caída de tensión ni reinicio; no se aporta una captura serial de esta etapa. Se propone conectar VIN a JD-VCC con USB desconectado, conservar el jumper retirado y comprobar reposo, tensiones y STATUS en DRY_RUN, todavía sin sondas, pantalla ni cargas en los bornes. Alimentar las bobinas no equivale a acreditar su activación o el cierre de NO/COM; estas comprobaciones siguen pendientes.

### DRY_RUN con alimentación del módulo y sin sondas

El usuario confirma las tres tensiones solicitadas en el módulo: JD-VCC aproximadamente 5 V, VCC e IN1 aproximadamente 3,3 V. Informa que ejecutó accidentalmente otra vez el comando de carga. El log posterior acredita ejecución de DRY_RUN, salida OFF al arrancar y ROM found=0. STATUS a uptime 19: SENSOR_FAULT, ambas sondas ausentes, request=active=relay=0, lockout=281, desired=applied=18, ciclos=970 y max_gap_ms=21. No se aporta resumen de carga; el arranque confirma que ejecuta DRY_RUN después de esa operación.

El prefijo ROM pegado está parcialmente deformado, aunque BOOT y STATUS son legibles. No se marca resuelta la corrupción serial anterior ni se acredita estabilidad prolongada o alimentación con bobina activada. El siguiente ensayo previsto reconecta únicamente MOSTO, con USB desconectado durante la maniobra, alimentación de sonda a 3V3, GND común y datos a GPIO 4, conservando DRY_RUN. AMBIENTE seguirá ausente durante esa etapa; no se requiere nueva carga.

### Recuperación con las dos sondas reconectadas

El usuario aporta ambas ROM presentes, recuperación de SENSOR_FAULT a BOOT_HOLD y SENSOR_AVAILABLE de MOSTO y AMBIENTE. STATUS a uptime 41: MOSTO 22,250 y AMBIENTE 24,625, ambas válidas, desired=applied=18, request=1, active=relay=0, lockout=259, degraded=0, fault=none, ciclos=2040 y max_gap_ms=26. Aunque se había propuesto reconectar una sola sonda, el log acredita las dos presentes; no se requiere repetir la etapa individual.

El usuario señala exceso de mediciones. Las tensiones de reposo ya verificadas no se vuelven a solicitar. El siguiente ensayo acotado propone HARDWARE sin cargas en los bornes ni compresor: observar el hold de 300 s, indicador/clic al activar y continuidad NO/COM (4/5 del canal R1) antes y después de MAINT ON, sin mover las puntas hacia alimentación. Este ensayo sigue pendiente. Los prefijos ROM pegados continúan parcialmente deformados; no se marca resuelto el problema serial ni la causa del apagado anterior.

### Activación y corte por mantenimiento en HARDWARE

El usuario confirma que toda la prueba solicitada ocurrió según lo esperado, incluyendo indicador/clic y continuidad NO/COM al activar, y apertura al entrar en mantenimiento. Las mediciones de contactos son evidencia comunicada por el usuario; no se cuenta con registro independiente del instrumental.

El log aporta BOOT_HOLD a uptime 299, ambas sondas válidas, request=1, active=relay=0 y lockout=1. A continuación se registra BOOT_HOLD -> COOLING y COMPRESSOR_START mode=HARDWARE physical_relay=1. STATUS a uptime 306: MOSTO 22,125, AMBIENTE 24,000, request=active=relay=1, lockout=0 y fault=none. MAINT ON provoca COOLING -> MAINTENANCE, COOLING_REQUEST off y COMPRESSOR_STOP mode=HARDWARE physical_relay=0. STATUS a uptime 332: MAINTENANCE, request=active=relay=0 y lockout=297. Consigna aplicada 18, wifi=mqtt=0, degraded=0 y max_gap_ms=29 durante la prueba.

Se acredita el hold de arranque, activación del contacto y corte por mantenimiento en este ensayo sin compresor. Se mantiene MAINTENANCE al finalizar. Esto no equivale a validar refrigeración real, el reinicio del contacto al terminar un lockout posterior al corte, corte físico por pérdida de MOSTO, pérdida/restauración de red previamente conectada ni resolución de la corrupción serial intermitente. El usuario atribuye el incidente anterior a la maniobra de medición; no se identificó eléctricamente el mecanismo concreto y no se repiten mediciones de tensión de reposo.

### Ciclo manual por temperatura, sin heladera

El usuario informa resultado satisfactorio del ensayo con enfriamiento y calentamiento manual de MOSTO, y aporta la secuencia Serial en HARDWARE. AMBIENTE permanece válida durante todo el fragmento. Se conserva SP=18 y HYST=0,3, wifi=mqtt=0, degraded=0 y max_gap_ms=29.

MAINT OFF produce COMPRESSOR_LOCKOUT remaining=101, seguido de COOLING cuando termina ese bloqueo. Al enfriar MOSTO aparece COOLING -> IDLE con T=16,50, COOLING_REQUEST off y COMPRESSOR_STOP physical_relay=0. Al recalentar aparece IDLE -> COMPRESSOR_LOCKOUT con T=18,75 y remaining=262: la demanda no activa inmediatamente la salida.

| Uptime (s) | Estado | MOSTO (°C) | Request / active / relay | Lockout (s) |
|---|---|---|---|---|
| 664 | IDLE | 15,875 | 0 / 0 / 0 | 283 |
| 779 | COMPRESSOR_LOCKOUT | 26,500 | 1 / 0 / 0 | 168 |
| 825 | COMPRESSOR_LOCKOUT | 26,000 | 1 / 0 / 0 | 121 |
| 954 | COOLING | 25,125 | 1 / 1 / 1 | 0 |
| 969 | IDLE | 11,875 | 0 / 0 / 0 | 294 |
| 979 | IDLE | 9,625 | 0 / 0 / 0 | 284 |
| 1003 | MAINTENANCE | 8,375 | 0 / 0 / 0 | 260 |

Entre los STATUS 825 y 954 se registra COMPRESSOR_LOCKOUT -> COOLING con T=25,25 y COMPRESSOR_START physical_relay=1. Un segundo enfriamiento produce COOLING -> IDLE con T=17,12 y corte physical_relay=0. La prueba termina con MAINT ON; un comando mal escrito anterior fue rechazado.

Se acredita corte al enfriar por debajo de SP-HYST, reaparición de demanda al superar SP+HYST y nuevo encendido después del bloqueo. Los contadores son coherentes con un apagado alrededor de uptime 647 y protección de 300 s; los eventos pegados no tienen timestamp propio, por lo que no se asigna un instante exacto de activación. Las lecturas saltan a 16,50 y 18,75 en las transiciones: el ensayo no caracteriza los límites exactos de la banda ni calibra la sonda. No hubo refrigeración real ni medición independiente de contactos en este nuevo fragmento. El siguiente ensayo previsto retira el cable de datos común GPIO 4 mientras COOLING para comprobar corte físico al perder MOSTO (y AMBIENTE simultáneamente); no se presenta como pérdida aislada de MOSTO.

### Pérdida del bus OneWire en HARDWARE

Después de MAINT OFF, MOSTO todavía fría mantiene IDLE: a uptime 1147, T=15,375, request=active=relay=0 y lockout=116. A uptime 1328, T=17,125 y lockout=0, la demanda sigue apagada. Al superar el umbral aparece IDLE -> COOLING con T=19,38 y COMPRESSOR_START physical_relay=1; STATUS a uptime 1442 confirma T=22,625, ambas sondas válidas y request=active=relay=1.

El usuario ejecuta la retirada del cable de datos común GPIO 4 y comunica resultado satisfactorio con los logs: COOLING -> SENSOR_FAULT, fault mosto_sensor, COOLING_REQUEST off, COMPRESSOR_STOP mode=HARDWARE physical_relay=0 y SENSOR_LOST disconnected para MOSTO y AMBIENTE. STATUS a uptime 1466: ambas temperaturas nan, ambas inválidas, request=active=relay=0, lockout=290, degraded=1, fault=mosto_sensor, desired=applied=18, wifi=mqtt=0 y max_gap_ms=29. No hubo reinicio visible del contador de uptime ni pérdida del monitor en este fragmento.

El log acredita desactivación de la salida HARDWARE ante la pérdida de MOSTO junto con AMBIENTE. La comunicación del usuario no desglosa en esta respuesta una nueva observación de indicador/contacto ni la latencia exacta desde retirar el cable; no se inventan esas mediciones. Recuperación de las sondas, guard después de la falla y nuevo encendido todavía pendientes en este ensayo. No equivale a probar pérdida aislada de AMBIENTE en HARDWARE.

### Recuperación del bus OneWire y activación posterior

El usuario confirma IN1 encendido y aporta SENSOR_FAULT -> COOLING con T=20,88, FAULT_RECOVERED guard still applies, COOLING_REQUEST on, COMPRESSOR_START mode=HARDWARE physical_relay=1 y SENSOR_AVAILABLE de ambas sondas. STATUS final a uptime 2610: MOSTO 20,875 y AMBIENTE 21,750, ambas válidas, request=active=relay=1, lockout=0, degraded=0, fault=none, applied=desired=18, wifi=mqtt=0 y max_gap_ms=29.

El STATUS final ocurre 1144 s después del STATUS de falla a uptime 1466. Los eventos de reconexión no tienen timestamp, por lo que este fragmento no permite fijar el instante de recuperación ni comprobar una recuperación dentro de los primeros 300 s después del corte. La transición directa a COOLING es admisible si el intervalo OFF ya terminó; no se interpreta por sí sola como elusión de la protección. Se acredita recuperación de sensores y nueva activación del indicador después de la falla, sin afirmar una medición independiente del contacto ni el timing exacto de esa recuperación. Se solicita finalizar con MAINT ON; esa acción todavía no está confirmada en este último fragmento.

Para la prueba siguiente de transporte se revisó network.cpp: el firmware usa WiFiClient/PubSubClient hacia MQTT_SERVER:1883 y los topics existentes. HARDWARE mantiene consignas MQTT y OTA deshabilitadas; el entorno esp32-mqtt-test permite consignas remotas con salida DRY_RUN. Antes de seleccionar el broker de prueba falta conocer si edge-01 está en la misma LAN que el ESP32 o solo es accesible desde el equipo del usuario por Tailscale. No se modifica Node-RED ni ningún servicio remoto para inferir esa conectividad.

### Preparación de conectividad LAN

El usuario confirma que edge-01 y ESP32 están en la misma LAN. Con permiso de red del entorno, se comprueba por SSH en solo lectura la dirección LAN del nodo y escucha TCP 1883 en sus interfaces. No se modifica ningún servicio remoto. Se omiten las direcciones privadas de este registro destinado al repositorio público.

Se compara secrets.ini local con secrets.ini.example sin mostrar valores: las cuatro entradas locales coinciden con la plantilla. Esto explica la falta de conectividad con la red real en las compilaciones usadas; no es una prueba de pérdida de una conexión previamente establecida. Se verifica que secrets.ini está ignorado por Git y se cambia solamente mqtt_broker a la dirección LAN comprobada. SSID y clave Wi-Fi quedan pendientes de completar por el usuario en el archivo local abierto en el editor; no se solicitan claves por chat ni se copian de otros archivos. OTA sigue deshabilitada y no necesita una clave real para esta prueba.

La siguiente carga prevista conserva HARDWARE, ACCEPT_MQTT_SETPOINTS=0 y ENABLE_OTA=0 para observar conexión y telemetría usando consignas por Serial. No se habilita el entorno esp32-mqtt-test ni se publican consignas en birra/setpoint durante esta preparación. La carga con datos Wi-Fi reales y la conexión todavía no están confirmadas.

### Conexión y telemetría reales — 2026-10-07

Después de completar la configuración Wi-Fi local y cargar, el usuario aporta BOOT mode=HARDWARE, relay=OFF, hold=300s, remote_setpoints=0 y OTA=0. Se identifican ambas ROM; después de la validación inicial aparecen SENSOR_AVAILABLE de MOSTO/AMBIENTE, WIFI_RECOVERED y MQTT_RECOVERED. Una consigna MQTT se rechaza con commands disabled for physical baseline tests; el usuario no publicó esa consigna como parte de este ensayo y no se identifica su origen en este log.

El error inicial Preferences nvs_open NOT_FOUND corresponde al espacio HARDWARE aún sin configuración guardada; se usan SP=18/HYST=0,3 por defecto y no aparece fallo posterior de configuración en el fragmento. El usuario envía MAINT ON y a uptime 122 se registra MAINTENANCE, MOSTO 20,875 y AMBIENTE 23,750 válidas, request=active=relay=0, lockout=178, wifi=mqtt=1, degraded=0, fault=none, ciclos=6111 y max_gap_ms=26.

El agente lee una publicación de birra/telemetria mediante mosquitto_sub dentro del broker, por SSH, sin publicar ni modificar servicios. Se conserva el JSON en [evidencia MQTT](evidence/mqtt-maintenance-2026-10-07.json). La muestra registra uptime=170, message_seq=17, control_cycles=8492, MAINTENANCE, dry_run=false, wifi=mqtt=true, ambos sensores válidos y relay=false. SP aplicado 18, fault=null, wifi_losses=mqtt_losses=0, dropped_logs=dropped_commands=0 y control_max_gap_ms=26. Los valores son coherentes con el Serial y el contador avanza desde uptime 122; los ceros corresponden a esta muestra, no prueban ausencia de pérdida histórica en otros ensayos.

El prefijo ROM pegado sigue parcialmente deformado; esta telemetría válida no resuelve la corrupción UART previa. Conexión inicial y recepción real están acreditadas. Pérdida/restauración de MQTT y de Wi-Fi siguen pendientes; se consulta si el broker es exclusivo del fermentador antes de elegir una interrupción breve que afectaría a todos sus clientes. No se detiene todavía ningún servicio.

El usuario confirma broker exclusivo del fermentador. Se prepara un helper local para detener únicamente ese contenedor durante 30 s y restaurarlo mediante trap, comprobando que inicialmente y al finalizar está ejecutándose. No cambia configuración, datos, Node-RED, InfluxDB ni Grafana. Se verifica sintaxis y recuperación con dobles locales: ejecución normal, fallo del stop, broker inicialmente detenido (sin iniciarlo) y fallo de restauración reportado. Esa verificación no detiene un broker real ni prueba recuperación real. El ensayo requiere observar COOLING antes de ejecutarlo, mantener MOSTO por encima de 18,3, compresor desconectado, monitor abierto y STATUS durante/después de la pausa. El helper aún no se ejecutó contra el servidor.

### Pérdida/restauración real de MQTT — 2026-10-07

El usuario confirma que IN1 permaneció encendido durante la interrupción y aporta eventos/STATUS antes, durante y después. MAINT OFF produce COOLING y COMPRESSOR_START physical_relay=1. La consigna aplicada permanece en 18, HYST=0,3, MOSTO 21,000 y AMBIENTE 23,625 válidas; no cambia la demanda ni la salida durante la prueba.

| Uptime (s) | Wi-Fi / MQTT | Estado | Request / active / relay | Ciclos | Max gap (ms) |
|---|---|---|---|---|---|
| 429 | 1 / 1 | COOLING | 1 / 1 / 1 | 21487 | 26 |
| 468 | 1 / 0 | COOLING | 1 / 1 / 1 | 23388 | 26 |
| 504 | 1 / 1 | COOLING | 1 / 1 / 1 | 25212 | 26 |

Se registra MQTT_LOST applied setpoint retained; local control continues, con errores TCP connection reset by peer y reintentos aproximadamente cada 5 s durante la pausa. Después aparece MQTT_RECOVERED y rechazo de consigna remota por estar deshabilitadas las órdenes MQTT. No hay reinicio visible del uptime, SENSOR_FAULT, internal_error ni cambio de estado del controlador en el fragmento. Los ciclos avanzan con MQTT desconectado y max_gap_ms no crece respecto de la muestra inicial. No se inventa la duración exacta de la indisponibilidad a partir de eventos sin timestamp; el helper estaba configurado para una pausa de 30 s, además de los tiempos de parada/inicio y reconexión.

Se acredita pérdida/restauración de MQTT mientras el control local mantiene salida activa, junto con observación física de IN1 por el usuario. No hay heladera ni compresor conectados. Esta prueba mantiene Wi-Fi conectado; todavía no acredita pérdida/restauración de Wi-Fi. El último STATUS sigue en COOLING; la finalización con MAINT ON aún no aparece en este fragmento. Se consulta disponibilidad para apagar temporalmente el Wi-Fi utilizado por la placa antes de elegir la prueba siguiente.

El usuario confirma que puede desactivar temporalmente ese Wi-Fi. Se propone mantener ESP32 por USB, monitor abierto, broker ejecutándose y MOSTO>18,3; registrar STATUS con COOLING/wifi=mqtt=1, apagar el Wi-Fi/punto de acceso unos 30 s, registrar WIFI_LOST/MQTT_LOST y STATUS con wifi=mqtt=0 conservando control, restaurar el Wi-Fi y comprobar WIFI_RECOVERED/MQTT_RECOVERED. Finalizar MAINT ON. No requiere firmware nuevo ni modificar servicios del servidor. La ejecución y resultados todavía están pendientes.

### Pérdida/restauración real de Wi-Fi — 2026-10-07

El usuario confirma IN1 encendido durante la pérdida de Wi-Fi y aporta WIFI_LOST, MQTT_LOST, WIFI_RECOVERED y MQTT_RECOVERED. SP aplicado/solicitado se mantiene en 18, HYST=0,3, ambas sondas válidas, degraded=0 y fault=none. Ningún evento muestra cambio de estado de control durante la caída/restauración.

| Uptime (s) | Wi-Fi / MQTT | Estado | Request / active / relay | MOSTO / AMBIENTE (°C) | Ciclos | Max gap (ms) |
|---|---|---|---|---|---|---|
| 681 | 1 / 1 | COOLING | 1 / 1 / 1 | 20,875 / 23,500 | 34071 | 26 |
| 836 | 0 / 0 | COOLING | 1 / 1 / 1 | 21,000 / 23,375 | 41821 | 27 |
| 890 | 1 / 1 | COOLING | 1 / 1 / 1 | 21,000 / 23,375 | 44513 | 52 |

El último STATUS de conexión anterior era uptime 504; la tabla utiliza 681 como muestra inmediatamente anterior a los eventos de pérdida. Los eventos no incluyen timestamp propio: no se deriva duración exacta de la caída de la diferencia entre consultas. No hay reinicio visible del uptime; sensores/ciclos avanzan y se conserva la salida física según IN1 observado por el usuario. Una consigna MQTT posterior a recuperar la conexión se rechaza por mantener remote_setpoints=0.

max_gap_ms aumenta de 26 a 27 durante la caída y a 52 después de recuperar la red. El firmware programa ciclos de 20 ms y enclava internal_error si el gap supera 250 ms (src/main.cpp). Por tanto hay variación temporal observable, pero no se alcanzó ese umbral en la muestra; no se afirma jitter nulo ni garantía de latencia para otras cargas. MAINT ON final registra COOLING -> MAINTENANCE, COOLING_REQUEST off y COMPRESSOR_STOP physical_relay=0. No hay STATUS posterior en este fragmento, pero el evento confirma el comando de corte. No hubo heladera ni compresor.

Queda acreditada pérdida/restauración real de Wi-Fi con control local activo. La siguiente prueba de seguridad prevista es reiniciar mediante EN/RESET mientras COOLING en HARDWARE, observar OFF al reiniciar y mantener la demanda sin eludir BOOT_HOLD de 300 s. Los ensayos de arranque anteriores y reset/reconexión en DRY_RUN no sustituyen este caso concreto. No se requiere volver a cargar firmware.

### Reinicio mientras COOLING en HARDWARE — 2026-10-07

El usuario confirma explícitamente que IN1 se apagó al pulsar EN/RESET y permaneció apagado durante los cinco minutos de BOOT_HOLD. Aporta STATUS del nuevo uptime 78 y 128, con ambas sondas válidas, demanda de frío y active=relay=0, lockout=222 y 172 respectivamente. SP aplicado/solicitado 18, HYST=0,3, MOSTO 20,875 y Wi-Fi/MQTT conectados. Se registran WIFI_RECOVERED/MQTT_RECOVERED y rechazo de una consigna remota, todavía deshabilitada.

Después aparece BOOT_HOLD -> COOLING, COMPRESSOR_START mode=HARDWARE physical_relay=1 y STATUS a uptime 308: request=active=relay=1, lockout=0, ambas sondas válidas y fault=none. MAINT ON final produce COMPRESSOR_STOP physical_relay=0; STATUS a uptime 347 confirma MAINTENANCE, request=active=relay=0 y lockout=294. El usuario también confirma apagado de IN1 con mantenimiento. Los ciclos avanzan 3937 -> 6412 -> 15417 -> 17345 y max_gap_ms=26 en las muestras.

Este fragmento no incluye el bloque BOOT ni el STATUS inmediatamente anterior a pulsar reset; la maniobra y observación física se acreditan mediante la confirmación explícita del usuario, junto con el nuevo uptime y la espera observada. No se inventa el instante exacto del evento de arranque sin timestamp. Se acredita OFF al reset y BOOT_HOLD en la prueba manual solicitada, sin compresor. El montaje queda en MAINTENANCE.

Los casos manuales ejecutados cubren corte por temperatura, bloqueo entre ciclos, falla del bus de sensores, mantenimiento, reinicio y pérdida/restauración de Wi-Fi/MQTT. La etapa completa aún no se declara aceptada: refrigeración real, polarización antes de setup y transitorios breves, diagnóstico de la corrupción UART intermitente y los límites de cada ensayo permanecen documentados. No se implementa ML ni se habilitan perfiles o consignas remotas.
