#include <Arduino.h>
#include <esp_task_wdt.h>
#include <esp_system.h>
#include <stdarg.h>
#include "runtime.h"
#include "sensor_reader.h"
#include "cooling_output.h"

class RelayPin {
public:
    void prepareOff() {
        // Preparar el latch HIGH antes de habilitar la salida ACTIVE LOW.
        digitalWrite(PIN_RELE_FRIO, HIGH);
        pinMode(PIN_RELE_FRIO, OUTPUT);
        digitalWrite(PIN_RELE_FRIO, HIGH);
    }
    void writeHigh(bool high) { digitalWrite(PIN_RELE_FRIO, high ? HIGH : LOW); }
};
static RelayPin relayPin;
static CoolingOutput<RelayPin> coolingOutput(relayPin, DRY_RUN);
QueueHandle_t commands = nullptr, logQueue = nullptr, saveQueue = nullptr;
static portMUX_TYPE sharedMux = portMUX_INITIALIZER_UNLOCKED;
static Snapshot current;
static TransportStatus transport;
static bool otaHold = false;

Snapshot snapshot() {
    portENTER_CRITICAL(&sharedMux);
    Snapshot result = current;
    portEXIT_CRITICAL(&sharedMux);
    return result;
}
void updateSnapshot(const Snapshot& value) {
    portENTER_CRITICAL(&sharedMux);
    current = value;
    portEXIT_CRITICAL(&sharedMux);
}
TransportStatus transportStatus() {
    portENTER_CRITICAL(&sharedMux);
    TransportStatus result = transport;
    portEXIT_CRITICAL(&sharedMux);
    return result;
}
void updateTransport(bool wifi, bool mqtt) {
    portENTER_CRITICAL(&sharedMux);
    if (transport.wifi && !wifi) ++transport.wifiLosses;
    if (transport.mqtt && !mqtt) ++transport.mqttLosses;
    transport.wifi = wifi;
    transport.mqtt = mqtt;
    portEXIT_CRITICAL(&sharedMux);
}
bool otaMaintenance() {
    portENTER_CRITICAL(&sharedMux);
    bool result = otaHold;
    portEXIT_CRITICAL(&sharedMux);
    return result;
}
void latchOtaMaintenance() {
    portENTER_CRITICAL(&sharedMux);
    otaHold = true; // Una OTA fallida requiere reinicio; no reanudar automáticamente.
    portEXIT_CRITICAL(&sharedMux);
}
bool enqueue(Command command) {
    if (xQueueSend(commands, &command, 0) == pdTRUE) return true;
    portENTER_CRITICAL(&sharedMux);
    ++transport.droppedCommands;
    portEXIT_CRITICAL(&sharedMux);
    logEvent("[COMMAND_REJECTED] queue full; applied setpoint unchanged");
    return false;
}
void logEvent(const char* format, ...) {
    char message[192];
    va_list args;
    va_start(args, format);
    vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    if (!logQueue || xQueueSend(logQueue, message, 0) != pdTRUE) {
        portENTER_CRITICAL(&sharedMux);
        ++transport.droppedLogs;
        portEXIT_CRITICAL(&sharedMux);
    }
}

static void controlTask(void*) {
    thermal::Controller controller;
    SensorReader reader;
    const Snapshot configuration = snapshot();
    controller.boot(millis());
    controller.setpoint(configuration.applied);
    controller.hysteresis(configuration.hysteresis);
    if (esp_task_wdt_add(nullptr) != ESP_OK) controller.fail();
    reader.begin();
    reader.diagnose(); // Aún no hay autorización de refrigeración.
    Snapshot previous;
    uint32_t lastCycle = millis(), cycles = 0, maxGap = 0;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        const uint32_t now = millis();
        const uint32_t gap = uint32_t(now - lastCycle);
        lastCycle = now;
        if (gap > maxGap) maxGap = gap;
        if (gap > 250) {
            controller.fail(); // Un plazo perdido no permite continuar refrigerando.
            logEvent("[INTERNAL_ERROR] control deadline missed: %lu ms", static_cast<unsigned long>(gap));
        }
        bool diagnose = false;
        Command command;
        // Trabajo acotado incluso si la red inunda la cola.
        for (unsigned i = 0; i < 4 && xQueueReceive(commands, &command, 0) == pdTRUE; ++i) {
            switch (command.type) {
                case CommandType::SETPOINT: {
                    logEvent("[SETPOINT_RECEIVED] source=%s value=%.3f", command.remote ? "MQTT" : "SERIAL", command.value);
                    if (controller.setpoint(command.value)) {
                        SavedConfig config{controller.applied(), controller.hysteresis()};
                        xQueueOverwrite(saveQueue, &config);
                    } else logEvent("[SETPOINT_REJECTED] range; applied=%.3f", controller.applied());
                    break;
                }
                case CommandType::REJECT_SETPOINT:
                    controller.setpoint(NAN);
                    logEvent("[SETPOINT_REJECTED] invalid payload; applied=%.3f", controller.applied());
                    break;
                case CommandType::HYSTERESIS:
                    if (controller.hysteresis(command.value)) {
                        SavedConfig config{controller.applied(), controller.hysteresis()};
                        xQueueOverwrite(saveQueue, &config);
                        logEvent("[CONFIG] hysteresis=%.3f", controller.hysteresis());
                    } else logEvent("[CONFIG_REJECTED] hysteresis must be 0.05..2.00");
                    break;
                case CommandType::MAINTENANCE:
                    controller.maintenance(command.value != 0);
                    logEvent("[MAINTENANCE] %s", command.value != 0 ? "enabled" : "released; guard still applies");
                    break;
                case CommandType::DIAGNOSE:
                    controller.maintenance(true);
                    diagnose = true;
                    break;
#if DRY_RUN
                case CommandType::SIM_MOSTO: reader.simulate(true, command.value); break;
                case CommandType::SIM_AMBIENTE: reader.simulate(false, command.value); break;
                case CommandType::SIM_CLEAR: reader.clearSimulation(); break;
#else
                case CommandType::SIM_MOSTO:
                case CommandType::SIM_AMBIENTE:
                case CommandType::SIM_CLEAR: logEvent("[COMMAND_REJECTED] simulation unavailable in HARDWARE"); break;
#endif
                default: controller.fail(); logEvent("[INTERNAL_ERROR] unknown command"); break;
            }
        }
        reader.poll(now);
        Snapshot next;
        next.mosto = reader.mosto(now);
        next.ambiente = reader.ambiente(now);
        next.decision = controller.tick(now, next.mosto, next.ambiente, otaMaintenance());
        coolingOutput.set(next.decision); // Única aplicación del comando físico.
        next.relay = coolingOutput.active();
        next.desired = controller.desired();
        next.applied = controller.applied();
        next.hysteresis = controller.hysteresis();
        next.uptimeMs = controller.uptimeMs();
        next.rejected = controller.rejected();
        next.cycles = ++cycles;
        next.maxGapMs = maxGap;
        updateSnapshot(next);
        if (next.decision.state != previous.decision.state) {
            logEvent("[CONTROL] %s -> %s | T=%.2f SP=%.2f", thermal::stateName(previous.decision.state),
                thermal::stateName(next.decision.state), next.mosto.temperature, next.applied);
            if (next.decision.state == thermal::State::SENSOR_FAULT) logEvent("[SENSOR_FAULT] %s", next.decision.fault);
            if (previous.decision.state == thermal::State::SENSOR_FAULT && !next.decision.fault) logEvent("[FAULT_RECOVERED] guard still applies");
            if (next.decision.state == thermal::State::COMPRESSOR_LOCKOUT) logEvent("[COMPRESSOR_LOCKOUT] remaining=%lu s", static_cast<unsigned long>((next.decision.lockoutRemainingMs + 999) / 1000));
        }
        if (next.decision.coolingRequest != previous.decision.coolingRequest) logEvent("[COOLING_REQUEST] %s", next.decision.coolingRequest ? "on" : "off");
        if (next.decision.coolingActive != previous.decision.coolingActive) logEvent("[COMPRESSOR_%s] mode=%s physical_relay=%d", next.decision.coolingActive ? "START" : "STOP", DRY_RUN ? "DRY_RUN" : "HARDWARE", next.relay);
        if (next.mosto.valid != previous.mosto.valid) logEvent("[SENSOR_%s] MOSTO reason=%s", next.mosto.valid ? "AVAILABLE" : "LOST", thermal::sensorFaultName(next.mosto.fault));
        if (next.ambiente.valid != previous.ambiente.valid) logEvent("[SENSOR_%s] AMBIENTE reason=%s", next.ambiente.valid ? "AVAILABLE" : "LOST", thermal::sensorFaultName(next.ambiente.fault));
        previous = next;
        if (diagnose) reader.diagnose(); // El relé ya está OFF y queda en MAINTENANCE.
        if (esp_task_wdt_reset() != ESP_OK) controller.fail();
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(20));
    }
}

// Persistencia se abre únicamente con el relé ya apagado; servicios la escriben.
extern SavedConfig loadConfiguration();
static void startupFailure(const char* reason) {
    coolingOutput.begin();
    Serial.printf("[INTERNAL_ERROR] %s; relay OFF; restart required\n", reason);
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}
void setup() {
    coolingOutput.begin(); // Antes de Serial, NVS, sensores o Wi-Fi.
    Serial.begin(115200);
    Serial.printf("[BOOT] mode=%s reset_reason=%d relay=OFF boot_hold=300s remote_setpoints=%d OTA=%d\n",
        DRY_RUN ? "DRY_RUN" : "HARDWARE", static_cast<int>(esp_reset_reason()), ACCEPT_MQTT_SETPOINTS, ENABLE_OTA);
    commands = xQueueCreate(8, sizeof(Command));
    logQueue = xQueueCreate(32, 192);
    saveQueue = xQueueCreate(1, sizeof(SavedConfig));
    if (!commands || !logQueue || !saveQueue) startupFailure("queue allocation failed");
    SavedConfig config = loadConfiguration();
    current.applied = current.desired = config.setpoint;
    current.hysteresis = config.hysteresis;
    if (esp_task_wdt_init(3, true) != ESP_OK) startupFailure("watchdog initialization failed");
    if (xTaskCreatePinnedToCore(servicesTask, "services", 6144, nullptr, 1, nullptr, 1) != pdPASS) startupFailure("services task failed");
    if (xTaskCreatePinnedToCore(controlTask, "thermal", 6144, nullptr, 4, nullptr, 1) != pdPASS) startupFailure("control task failed");
    if (xTaskCreatePinnedToCore(networkTask, "network", 8192, nullptr, 1, nullptr, 0) != pdPASS) {
        // La red es opcional: el control local sigue funcionando.
        logEvent("[NETWORK_ERROR] task unavailable; local control continues");
    }
}
void loop() { vTaskDelay(pdMS_TO_TICKS(1000)); }
