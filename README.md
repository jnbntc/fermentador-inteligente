# Fermentador inteligente

Sistema para controlar y observar la temperatura durante la fermentación de cerveza. Combina un ESP32, sensores y un relé de refrigeración con un servidor que administra perfiles, registra mediciones y muestra el proceso.

El objetivo es pasar de un perfil que avanza únicamente por calendario a un seguimiento por lote, con temperatura del mosto, condiciones exteriores y mediciones manuales de densidad. Las funciones adaptativas están en desarrollo: todavía no hay un modelo de aprendizaje automático entrenado ni validación con un lote real.

## Cómo controla la temperatura

El ESP32 lee dos sensores DS18B20: mosto y ambiente de referencia. Usa histéresis: con objetivo de 18 °C y banda de 0,3 °C solicita refrigeración por encima de 18,3 °C y la apaga a 17,7 °C o menos. El compresor debe permanecer apagado cinco minutos antes de volver a encenderse, también después de un reinicio o una falla del sensor.

Node-RED calcula la consigna según el perfil elegido y la envía por MQTT. El ESP32 publica temperaturas, estado del relé y consigna aplicada. InfluxDB conserva registros y Grafana permite consultar la evolución. El relé se controla en el ESP32; el servidor administra consignas y seguimiento.

~~~mermaid
flowchart LR
    Sensores[DS18B20: mosto y ambiente] --> ESP[ESP32: control local]
    ESP --> Rele[Relé de refrigeración]
    ESP <-->|MQTT| Broker[Mosquitto]
    Broker <--> NR[Node-RED: perfiles y alertas]
    NR --> DB[InfluxDB: mediciones]
    DB --> Grafana[Grafana: seguimiento]
~~~

La instalación actual controla refrigeración. No implementa una salida de calefacción: subir la consigna permite que la temperatura aumente por el entorno y el proceso, pero no garantiza alcanzar una temperatura superior al ambiente.

## Estado del proyecto

| Componente | Estado |
|---|---|
| Firmware ESP32, sensores, relé y display | Implementado; pruebas físicas pendientes para los cambios actuales |
| Comunicación MQTT y ajuste de consigna | Implementado |
| Node-RED, InfluxDB y Grafana | Existen en el servidor; integración reproducible pendiente |
| Protección compartida del compresor | Incluida en esta propuesta, con pruebas automatizadas |
| Catálogo versionado de recetas | Biblioteca SQLite inicial; interfaz e integración pendientes |
| Atenuación aparente y estabilidad de densidad | Cálculos iniciales probados; formulario de carga pendiente |
| Adaptación de etapas y confirmación de diacetilo | Diseño documentado; implementación pendiente |
| Aprendizaje automático con temperatura exterior | Planificado; requiere datos reales y validación |

Las recetas y mediciones actuales son pruebas. No se presentan como resultados de lotes reales. El antiguo agente predictivo vacío no constituye una implementación de machine learning.

## Hardware

- ESP32 DevKit v1.
- Dos DS18B20 en el bus OneWire, GPIO 4.
- Relé de refrigeración activo en nivel bajo, GPIO 26.
- Display TM1637, GPIO 18 y 19.

Las direcciones de sensores deben corresponder al montaje real. La temperatura interior de la cámara y la exterior son variables distintas; registrar la ubicación de cada sensor antes de entrenar un modelo.

## Compilar y cargar

El entorno utilizado es el espacio compartido `iot-dev` de [distrobox-stack](https://github.com/jnbntc/distrobox-stack), con PlatformIO. También puede usarse una instalación local compatible. La plataforma ESP32 está fijada en la versión 7.0.0, utilizada para verificar la compilación de esta propuesta.

~~~sh
cp secrets.ini.example secrets.ini
# Completar valores locales y elegir una contraseña OTA nueva.
pio run -e esp32doit-devkit-v1
~~~

`secrets.ini` queda excluido de Git. El ejemplo contiene valores de demostración. Si se utilizó la antigua contraseña OTA publicada en el código, reemplazarla al actualizar la placa: retirarla del archivo actual no la elimina del historial público.

~~~sh
pio run -e esp32doit-devkit-v1 -t upload
pio device monitor -e esp32doit-devkit-v1
~~~

OTA requiere conexión y la contraseña configurada. Al comenzar una actualización se apaga la refrigeración; la recuperación respeta la protección del compresor.

## Contrato MQTT actual

| Tópico | Dirección | Contenido |
|---|---|---|
| `birra/telemetria` | ESP32 → servidor | JSON: `mosto`, `ambiente`, `rele`, `setpoint` |
| `birra/setpoint` | servidor → ESP32 | Número en °C, mayor que 0 y menor que 30 |

Ejemplo simulado:

~~~json
{"mosto":18.4,"ambiente":22.1,"rele":1,"setpoint":18.0}
~~~

La consigna retenida permite recuperarla al reconectar. El contrato siguiente agregará dispositivo, lote, calidad de lectura y confirmación de comandos. El broker de pruebas permite acceso anónimo: antes del uso real deben configurarse autenticación, permisos por tópico y acceso protegido al editor de Node-RED.

## Recetas y densidad

`server/fermentation.py` permite guardar y recuperar versiones de recetas, validar etapas y calcular métricas con densidades específicas previamente corregidas.

~~~python
from server.fermentation import RecipeStore, apparent_attenuation

catalogo = RecipeStore("recipes.sqlite")
version = catalogo.save("perfil-prueba", {
    "name": "Perfil térmico de demostración",
    "stages": [{"day": 0, "temperature_c": 18}, {"day": 3, "temperature_c": 19}]
})
print(apparent_attenuation(1.050, 1.020))  # Aproximadamente 60 %
catalogo.close()
~~~

El perfil ilustra el formato; no es una recomendación cervecera. La biblioteca no inicia lotes ni envía consignas. La interfaz y su conexión al servidor son el siguiente paso.

La atenuación calculada es aparente: no mide directamente el porcentaje real de azúcares consumidos. Registrar instrumento, temperatura de muestra y correcciones. Una lectura cruda de refractómetro durante la fermentación no equivale a una densidad corregida.

El seguimiento permitirá sugerir etapas y revisar su duración dentro de los límites de la receta y la levadura. La densidad estable no mide diacetilo: su comprobación requiere un resultado manual registrado. [Referencia de White Labs](https://go.whitelabs.com/forced-diacetyl-testing).

## Pruebas sin la placa

~~~sh
python3 -m unittest discover -s test -p 'test_*.py' -v
g++ -std=c++11 -Wall -Wextra -Werror -Iinclude test/cooling_guard_test.cpp -o /tmp/cooling-guard-test
/tmp/cooling-guard-test
~~~

La compilación completa del firmware y las pruebas de la biblioteca de densidad y protección del compresor fueron verificadas sin la placa, con valores de configuración de demostración. Queda pendiente la verificación física de sensores, relé, compresor y cortes de energía. La integración continua está preparada, pero todavía no está activada en GitHub.

## Próximos pasos

1. Validar las correcciones con la placa y el montaje real.
2. Integrar catálogo, lotes y carga de densidad con Node-RED Dashboard.
3. Corregir estado, alarmas, respaldos y paneles del servidor.
4. Incorporar sugerencias de etapas por densidad y confirmaciones manuales.
5. Registrar datos reales y comparar un modelo térmico sencillo con aprendizaje automático.
6. Activar recomendaciones después de validar error, límites y ausencia de datos.

Ver [el diseño adaptativo](docs/control-adaptativo.md).
