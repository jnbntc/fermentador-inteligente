# Arquitectura de la baseline determinista

## Revisión de la base existente

La base tenía un único `src/main.cpp`: lectura DallasTemperature, decisión térmica, display, Wi-Fi, MQTT y OTA. `controlTermico()` mezclaba display y relé, y se llamaba cada diez segundos después de tareas de red. `PubSubClient.connect()` es síncrono aunque se limite la frecuencia de reintentos. El parser `String.toFloat()` aceptaba prefijos. Solo había comprobaciones parciales del sensor MOSTO y no se verificaba AMBIENTE.

Se reutilizan `CoolingGuard`, pines, ROM configuradas, librerías, tópicos, configuración privada y plataforma fijada. Las bibliotecas de recetas y sus pruebas se conservan sin integrarlas. Node-RED, InfluxDB y Grafana no se modifican. El cambio necesario en el firmware separa responsabilidades; no cambia hardware ni añade otro protocolo.

## Responsabilidades

| Componente | Responsabilidad |
|---|---|
| `thermal_controller.h` | Validación de muestras, configuración, histéresis y máquina de estados; C++ sin hardware |
| `cooling_guard.h` | Intervalo de apagado compartido por todas las causas |
| `cooling_output.h` | Aplicación ACTIVE LOW, estados desconocidos OFF y DRY_RUN |
| `sensor_reader.*` | Bus OneWire, conversión asíncrona, ROM, CRC vía DallasTemperature y diagnósticos |
| `main.cpp` | Boot OFF, colas, snapshots y tarea local; GPIO encapsulado |
| `network.cpp` | Wi-Fi/MQTT/OTA, únicamente comandos y snapshots |
| `services.cpp` | Serial, display y persistencia NVS, fuera de la tarea crítica |
| `telemetry.h` | JSON acotado y observable, sin dependencia de Arduino |

La tarea local corre en núcleo 1, prioridad 4 y período nominal de 20 ms. Sensores se solicitan aproximadamente cada segundo; conversión no bloqueante 375–750 ms. Servicios corren a menor prioridad en núcleo 1; red en núcleo 0. Colas sin espera y secciones críticas solo para copiar estructuras. No se comparte el cliente MQTT ni el bus OneWire entre tareas.

Perder más de 250 ms entre ciclos enclava error interno/OFF hasta reboot. El watchdog de la tarea usa tres segundos y panic habilitado. No es un dispositivo certificado ni permite garantizar OFF instantáneo ante toda corrupción física/CPU: si la CPU se bloquea, el watchdog debe reiniciar; la polarización externa debe mantener el relé OFF durante reset. Verificar ambos en el montaje real.

Persistir en flash puede pausar ejecución: es trabajo no crítico y cualquier incumplimiento del plazo se trata conservadoramente como error/OFF. Registrar `control_max_gap_ms` durante la prueba de configuración y carga de red. No relajar límites para ocultar un fallo antes de investigarlo.

## Prioridad y transiciones

La función de transición se evalúa cada ciclo en este orden. Desde cualquier estado puede ir a la primera condición aplicable:

| Condición | Estado | Salida |
|---|---|---|
| Error interno enclavado / estado corrupto | `SENSOR_FAULT`, fault=`internal_error` | OFF; solo reboot libera |
| Mantenimiento Serial o OTA | `MAINTENANCE` | OFF |
| MOSTO inválido/no reciente | `SENSOR_FAULT`, fault=`mosto_sensor` | OFF |
| MOSTO válido, menos de 300 s desde boot | `BOOT_HOLD` | OFF |
| No hay demanda por histéresis | `IDLE` | OFF |
| Hay demanda y falta intervalo desde apagado | `COMPRESSOR_LOCKOUT` | OFF |
| Hay demanda y guard autoriza | `COOLING` | ON en HARDWARE; OFF físico en DRY_RUN |

Solo `COOLING` con demanda activa y sin fault autoriza la abstracción de salida. Cualquier enum desconocido se traduce en OFF. Fuera del control, ningún consumidor escribe el relé.

Al recuperarse MOSTO necesita tres muestras consecutivas válidas; se recalcula la demanda y se aplica la espera pendiente. Salir de mantenimiento sigue el mismo criterio. Mantenimiento no borra errores internos. Reboot nunca restaura una salida ON. El boot hold se libera una sola vez por boot y no se reactiva por overflow de `millis()`.

Para SP=18 e histéresis=0,3: solicitar si T>18,3; apagar si T<=17,7; conservar demanda entre ambos umbrales. Una muestra invalidada borra demanda y fuerza apagado. Todos los apagados de un compresor activo actualizan el instante de referencia del guard; repetir OFF no extiende la espera.

## Sensores y datos

MOSTO admite -5..40 °C; AMBIENTE -20..60 °C. Son límites de esta instalación. -127, 85, valores no finitos o CRC/respuesta incorrectos siempre invalidan. Tres conversiones válidas consecutivas habilitan el sensor después de boot o falla. Más de cinco segundos sin nueva muestra válida/respuesta evaluada invalidan el estado. Una sonda que responde con temperatura constante no puede distinguirse de una temperatura realmente estable solamente por ese valor; no declarar un detector de congelamiento inexistente.

Se requiere alimentación de tres hilos. Alimentación parasitaria detectada al inicio falla conservadoramente. El escaneo ROM entra en mantenimiento antes de acceder al bus; devuelve hasta ocho dispositivos sin cambiar roles. Las muestras de simulación existen exclusivamente cuando se compila DRY_RUN.

Una consigna finita fuera de rango se registra como deseada pero no aplicada; un payload que ni siquiera se puede parsear conserva ambos valores y suma un rechazo. No se guarda el valor inválido. Histeresis y consigna aplicadas válidas se almacenan en NVS; fallo de NVS se informa y no invalida un control que sigue en RAM. Mantener el último valor en RAM no garantiza persistencia si se corta alimentación antes de completar la escritura.

La red puede pedir una consigna cuando se habilita explícitamente; no puede saltar sensor, mantenimiento, boot hold ni guard. Durante esta fase los entornos físicos rechazan consignas MQTT y OTA por defecto. Eso evita reactivar perfiles antiguos/retained mientras se verifica el cableado.

## Referencias de implementación

- [Watchdog de tareas, ESP-IDF 4.4](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/system/wdts.html).
- [DS18B20, alimentación, ROM y tiempos de conversión](https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf).
