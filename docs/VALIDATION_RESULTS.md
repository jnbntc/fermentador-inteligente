# Resultados de validación — baseline determinista

Actualizado el 2026-10-07. Las pruebas físicas fueron ejecutadas por el usuario desde iot-dev: el entorno del agente no puede abrir el puerto USB. El agente comprobó archivos de captura y recibió una publicación real en el broker. Todos los ensayos de relé se hicieron sin heladera, compresor ni cargas externas en los bornes.

## Software

Validación registrada el 2026-10-06:

- Cuatro compilaciones ESP32 aprobadas: DRY_RUN, HARDWARE, prueba MQTT en DRY_RUN y prueba OTA opcional en DRY_RUN.
- 16 escenarios C++ aprobados, incluidos A–J, recuperación, mantenimiento, error interno enclavado, overflow, parser estricto, ACTIVE LOW y DRY_RUN. También pasaron las pruebas previas de CoolingGuard.
- JSON normal/degradado y SENSOR_FAULT parseado y comprobado.
- Seis pruebas Python existentes aprobadas; recetas/densidad permanecen fuera del controlador.
- C++11 con -Wall -Wextra -Werror y revisión de espacios aprobados.

La prueba host de dos horas avanza tiempo virtual; no equivale a dos horas reales de desconexión sobre el dispositivo. Completar la configuración Wi-Fi privada permitió después cargar HARDWARE y conectarlo a la LAN. No se modificó el código C++ durante estos ensayos manuales; se configuró carga USB a 115200 para la recuperación del enlace.

## Pruebas de banco

| Caso | Resultado observado | Evidencia y límites |
|---|---|---|
| Sondas y roles | Ambas ROM detectadas; MOSTO/AMBIENTE diferenciadas y validadas | Pérdida/reconexión observada, tres conversiones exigidas por firmware |
| DRY_RUN | Salida física apagada con demanda lógica activa | GPIO 26 aproximadamente 3,3 V medido por el usuario |
| Contactos del módulo | Reposo COM/NC cerrado, NO/COM abierto; activación/corte según lo esperado | Continuidad comunicada por el usuario en canal R1; sin tensión externa en contactos |
| BOOT_HOLD | Salida apagada con demanda antes de 300 s y activación posterior | STATUS HARDWARE a 299: relay=0; a 306: relay=1 |
| Temperatura e intervalo OFF | Cortes a 16,50 y 17,12 °C, demanda al recalentar a 18,75 y nuevo encendido después del bloqueo | SP=18, HYST=0,3; no caracteriza límites exactos ni calibra las sondas |
| Falla del bus OneWire | SENSOR_FAULT y desactivación HARDWARE al perder ambas sondas | STATUS a 1466: relay=0, lockout=290. Recuperación posterior a 2610: ambas válidas y relay=1; IN1 encendido confirmado |
| Mantenimiento | MAINT ON corta salida y contacto; salir conserva el guard | Confirmación física del usuario y eventos COMPRESSOR_STOP; STATUS con bloqueo vigente |
| Reinicio mientras COOLING | IN1 apagado al pulsar EN/RESET y durante los cinco minutos siguientes | Confirmación explícita del usuario; BOOT_HOLD a 78/128 y COOLING a 308. Final MAINTENANCE a 347, relay=0 |
| Pérdida/restauración MQTT | Control local y SP=18 conservados; IN1 permaneció encendido | STATUS a 429/468/504: mqtt=1/0/1, wifi=1, COOLING. Ciclos 21487 -> 23388 -> 25212; gap máximo 26 ms |
| Pérdida/restauración Wi-Fi | Control local y SP=18 conservados; IN1 permaneció encendido | STATUS a 681/836/890: wifi/mqtt=1/1, 0/0, 1/1. Ciclos 34071 -> 41821 -> 44513; gap máximo 26 -> 27 -> 52 ms |
| Consignas inválidas | SP 30, SP nan y SP 18basura rechazadas conservando applied=18 en DRY_RUN | Persistencia de consigna también observada en DRY_RUN. Órdenes MQTT deshabilitadas en HARDWARE y rechazadas al conectar/reconectar |
| Telemetría real | Publicación recibida en birra/telemetria, JSON válido y coherente con Serial | [Muestra de mantenimiento](evidence/mqtt-maintenance-2026-10-07.json): uptime 170, secuencia 17, ciclos 8492, sensores válidos, wifi/mqtt=true, relay=false |

El mayor intervalo observado entre ciclos fue 52 ms después de recuperar Wi-Fi. El período nominal es 20 ms; el firmware enclava internal_error si supera 250 ms. No se alcanzó ese umbral en estas muestras, sin afirmar jitter nulo ni una latencia máxima garantizada bajo otras cargas.

El error NVS NOT_FOUND en el primer arranque HARDWARE refleja configuración aún no guardada en ese espacio: se usaron los valores por defecto. Hubo un apagado durante una maniobra de medición y una carga fallida; la placa aislada respondió a ROM, volvió a ejecutar DRY_RUN y completó las pruebas HARDWARE posteriores. No se identificó eléctricamente el mecanismo concreto del incidente.

El broker dedicado se interrumpió brevemente para la prueba MQTT y fue restaurado. No se desplegó código ni se cambió configuración de Node-RED, InfluxDB o Grafana. Se conserva el [registro completo y límites de cada ensayo](PHYSICAL_VALIDATION.md).

## Pendientes

- Refrigeración real, respuesta térmica de un volumen y comportamiento con un compresor conectado: FASE D pendiente.
- Confirmar polarización externa antes de setup y caracterizar transitorios breves de GPIO/contactos. El multímetro y el indicador no descartan pulsos demasiado cortos para observarlos.
- Diagnosticar corrupción UART intermitente: algunas capturas fueron limpias, otras registraron bytes no ASCII y flujo anómalo. No se declara resuelta por los últimos logs legibles.
- Caracterizar latencia exacta de detección de falla y recuperación dentro del guard después de perder MOSTO: en el ensayo HARDWARE el STATUS final llegó 1144 s después del STATUS de falla y los eventos de reconexión no tenían timestamp.
- Ensayos no acreditados todavía: pérdida aislada de AMBIENTE en HARDWARE, consignas MQTT inválidas con recepción habilitada en DRY_RUN, persistencia HARDWARE e integración de campos nuevos con InfluxDB/Grafana.

Los casos de banco registrados no habilitan una instalación de tensión de red ni equivalen a aceptación completa de la etapa. Se mantienen deshabilitados perfiles automáticos, consignas MQTT en HARDWARE y OTA; no se implementa ML ni control adaptativo.
