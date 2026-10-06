# Validación de software — 2026-10-06

- Cuatro compilaciones completas aprobadas: DRY_RUN, HARDWARE, prueba MQTT (DRY_RUN) y prueba OTA opcional (DRY_RUN).
- 16 escenarios C++ aprobados, incluidos A–J, recuperación, mantenimiento, error interno enclavado, overflow del contador, payload estricto, ACTIVE LOW y salida DRY_RUN. También se ejecutaron las pruebas previas de CoolingGuard.
- JSON de telemetría normal/degradada y SENSOR_FAULT parseado y comprobado.
- Seis pruebas Python existentes aprobadas; el catálogo permanece fuera del controlador.
- Revisión de espacios aprobada.

Pruebas host compiladas con C++11 y -Wall -Wextra -Werror. La simulación de dos horas sin transporte avanza tiempo virtual: no es una prueba física de desconexión ni una prueba real de dos horas.

El sistema detectó un CP2102/ttyUSB0. A pesar de autorizar el acceso al dispositivo, el entorno de ejecución no logró exponer el puerto serie. **No se cargó firmware ni se midieron sensores, GPIO o contactos físicos.** No se desplegó ningún cambio en edge-01.

La aceptación de hardware sigue pendiente según HARDWARE_VALIDATION.md. En particular: polaridad eléctrica del módulo, OFF durante boot/reset/carga, cinco minutos con salida real, recuperación de MOSTO y control mientras Wi-Fi/MQTT están caídos.
