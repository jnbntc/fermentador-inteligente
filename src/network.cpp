#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>
#include "runtime.h"
#include "telemetry.h"

#if !defined(WIFI_SSID) || !defined(WIFI_PASS) || !defined(MQTT_SERVER) || !defined(OTA_PASSWORD)
#error "Copiar secrets.ini.example a secrets.ini y completar la configuración local."
#endif

// Esta tarea es la única dueña de WiFiClient/PubSubClient/OTA. Nunca toca el relé.
static void receiveSetpoint(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, "birra/setpoint") != 0) return;
    float value;
    if (!thermal::parseNumber(reinterpret_cast<const char*>(payload), length, value)) {
        enqueue({CommandType::REJECT_SETPOINT, 0, true});
        return;
    }
if (!thermal::validSetpoint(value)) { enqueue({CommandType::SETPOINT, value, true}); return; }
#if ACCEPT_MQTT_SETPOINTS
    enqueue({CommandType::SETPOINT, value, true});
#else
    logEvent("[SETPOINT_REJECTED] MQTT commands disabled for physical baseline tests");
#endif
}

#if ENABLE_OTA
static void beginOta() {
    ArduinoOTA.setHostname("esp32-fermentador");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() {
        latchOtaMaintenance();
        const uint32_t began = millis();
        while (snapshot().decision.state != thermal::State::MAINTENANCE || snapshot().relay) {
            if (uint32_t(millis() - began) > 1000) ESP.restart();
            vTaskDelay(pdMS_TO_TICKS(10));
        }
        logEvent("[MAINTENANCE] OTA relay OFF acknowledged");
    });
    ArduinoOTA.onError([](ota_error_t error) { logEvent("[OTA_ERROR] %u; maintenance latched; restart required", error); });
    ArduinoOTA.begin();
}
#endif

void networkTask(void*) {
    WiFiClient socket;
    PubSubClient mqtt(socket);
    mqtt.setServer(MQTT_SERVER, 1883);
    mqtt.setCallback(receiveSetpoint);
    mqtt.setSocketTimeout(1);
    if (!mqtt.setBufferSize(1536)) { logEvent("[MQTT_ERROR] buffer unavailable; local control continues"); vTaskDelete(nullptr); return; }
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    char clientId[40];
    snprintf(clientId, sizeof(clientId), "Fermentador-%012llX", static_cast<unsigned long long>(ESP.getEfuseMac()));
    uint32_t lastAttempt = 0, lastPublished = 0, sequence = 0;
    bool firstAttempt = true, wasWifi = false, wasMqtt = false;
#if ENABLE_OTA
    bool otaReady = false;
#endif
    for (;;) {
        bool wifi = WiFi.status() == WL_CONNECTED;
        // Registrar pérdida ANTES de una llamada TCP que puede bloquear esta tarea.
        if (!wifi && mqtt.connected()) mqtt.disconnect();
        if (wasWifi && !wifi) logEvent("[WIFI_LOST] local control continues");
        if (!wasWifi && wifi) logEvent("[WIFI_RECOVERED]");
        wasWifi = wifi;
        bool connected = wifi && mqtt.connected();
        if (wasMqtt && !connected) { logEvent("[MQTT_LOST] applied setpoint retained; local control continues"); wasMqtt = false; }
        updateTransport(wifi, connected);
        const uint32_t now = millis();
        if (wifi && !connected && (firstAttempt || uint32_t(now - lastAttempt) >= 5000)) {
            firstAttempt = false;
            lastAttempt = now;
            connected = mqtt.connect(clientId);
            if (connected && !mqtt.subscribe("birra/setpoint")) { mqtt.disconnect(); connected = false; }
        }
        if (connected) mqtt.loop();
        connected = wifi && mqtt.connected();
        if (!wasMqtt && connected) logEvent("[MQTT_RECOVERED]");
        if (wasMqtt && !connected && wifi) logEvent("[MQTT_LOST] applied setpoint retained; local control continues");
        wasMqtt = connected;
        updateTransport(wifi, connected);
#if ENABLE_OTA
        if (wifi && !otaReady) { beginOta(); otaReady = true; }
        if (otaReady && wifi) ArduinoOTA.handle();
#endif
        if (connected && uint32_t(now - lastPublished) >= 10000) {
            lastPublished = now;
            const Snapshot s = snapshot();
            const TransportStatus t = transportStatus();
            thermal::Telemetry v;
            v.mosto = s.mosto; v.ambiente = s.ambiente; v.decision = s.decision;
            v.desired = s.desired; v.applied = s.applied; v.hysteresis = s.hysteresis;
            v.relay = s.relay; v.wifi = t.wifi; v.mqtt = t.mqtt; v.dryRun = DRY_RUN;
            v.uptimeMs = s.uptimeMs; v.sequence = ++sequence; v.cycles = s.cycles; v.rejected = s.rejected; v.maxGapMs = s.maxGapMs;
            v.wifiLosses = t.wifiLosses; v.mqttLosses = t.mqttLosses; v.droppedLogs = t.droppedLogs; v.droppedCommands = t.droppedCommands;
            char payload[1200];
            if (!thermal::telemetryJson(v, payload, sizeof(payload)) || !mqtt.publish("birra/telemetria", payload)) logEvent("[MQTT_ERROR] telemetry not sent");
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
