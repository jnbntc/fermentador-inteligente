#include <Preferences.h>
#include <initializer_list>
#include <TM1637Display.h>
#include "runtime.h"

static const char* nvsNamespace() { return DRY_RUN ? "ferm-dry" : "ferm-ctrl"; }
SavedConfig loadConfiguration() {
    SavedConfig result{18, 0.3f};
    Preferences preferences;
    if (preferences.begin(nvsNamespace(), true)) {
        float setpoint = preferences.getFloat("setpoint", 18);
        float hysteresis = preferences.getFloat("hysteresis", 0.3f);
        if (thermal::validSetpoint(setpoint)) result.setpoint = setpoint;
        else Serial.println("[CONFIG_REJECTED] invalid stored setpoint; default 18 C");
        if (thermal::validHysteresis(hysteresis)) result.hysteresis = hysteresis;
        else Serial.println("[CONFIG_REJECTED] invalid stored hysteresis; default 0.3 C");
        preferences.end();
    }
    return result;
}

static void saveConfiguration(const SavedConfig& config) {
    Preferences preferences;
    if (!preferences.begin(nvsNamespace(), false)) {
        logEvent("[CONFIG_ERROR] NVS unavailable; current control unaffected");
        return;
    }
    bool ok = true;
    if (preferences.getFloat("setpoint", NAN) != config.setpoint) ok = preferences.putFloat("setpoint", config.setpoint) == sizeof(float);
    if (preferences.getFloat("hysteresis", NAN) != config.hysteresis) ok = (preferences.putFloat("hysteresis", config.hysteresis) == sizeof(float)) && ok;
    preferences.end();
    if (!ok) logEvent("[CONFIG_ERROR] NVS write failed; current control unaffected");
}

void printStatus(const Snapshot& value) {
    const auto t = transportStatus();
    Serial.printf("[STATUS] %s T=%.3f mosto_valid=%d ambiente=%.3f ambiente_valid=%d desired=%.3f applied=%.3f hyst=%.3f request=%d active=%d relay=%d lockout=%lu wifi=%d mqtt=%d degraded=%d fault=%s uptime=%llu cycles=%lu max_gap_ms=%lu\n",
        thermal::stateName(value.decision.state), value.mosto.temperature, value.mosto.valid,
        value.ambiente.temperature, value.ambiente.valid, value.desired, value.applied, value.hysteresis,
        value.decision.coolingRequest, value.decision.coolingActive, value.relay,
        static_cast<unsigned long>((value.decision.lockoutRemainingMs + 999) / 1000), t.wifi, t.mqtt,
        value.decision.degraded, value.decision.fault ? value.decision.fault : "none",
        static_cast<unsigned long long>(value.uptimeMs / 1000), static_cast<unsigned long>(value.cycles), static_cast<unsigned long>(value.maxGapMs));
}

static void serialCommand(char* line) {
    float number;
    if (strcmp(line, "STATUS") == 0) { printStatus(snapshot()); return; }
    if (strcmp(line, "ROM") == 0) { enqueue({CommandType::DIAGNOSE}); return; }
    if (strcmp(line, "MAINT ON") == 0) { enqueue({CommandType::MAINTENANCE, 1}); return; }
    if (strcmp(line, "MAINT OFF") == 0) { enqueue({CommandType::MAINTENANCE, 0}); return; }
    if (strncmp(line, "SP ", 3) == 0) {
        if (thermal::parseNumber(line + 3, strlen(line + 3), number)) enqueue({CommandType::SETPOINT, number});
        else enqueue({CommandType::REJECT_SETPOINT});
        return;
    }
    if (strncmp(line, "HYST ", 5) == 0 && thermal::parseNumber(line + 5, strlen(line + 5), number)) {
        enqueue({CommandType::HYSTERESIS, number}); return;
    }
#if DRY_RUN
    if (strcmp(line, "SIM CLEAR") == 0) { enqueue({CommandType::SIM_CLEAR}); return; }
    for (const char* prefix : {"SIM MOSTO ", "SIM AMBIENTE "}) {
        const size_t length = strlen(prefix);
        if (strncmp(line, prefix, length) != 0) continue;
        if (strcmp(line + length, "OFF") == 0) number = NAN;
        else if (!thermal::parseNumber(line + length, strlen(line + length), number)) { logEvent("[COMMAND_REJECTED] invalid simulation"); return; }
        enqueue({prefix[4] == 'M' ? CommandType::SIM_MOSTO : CommandType::SIM_AMBIENTE, number});
        logEvent("[SIMULATION] %s", line);
        return;
    }
#endif
    logEvent("[COMMAND_REJECTED] use STATUS, ROM, SP n, HYST n, MAINT ON/OFF%s", DRY_RUN ? ", SIM MOSTO/AMBIENTE n/OFF, SIM CLEAR" : "");
}

static void displayTemperature(TM1637Display& display, const Snapshot& value) {
    if (!value.mosto.valid || value.decision.fault || value.decision.state == thermal::State::MAINTENANCE) {
        const uint8_t error[] = {SEG_G, SEG_G, SEG_G, SEG_G};
        display.setSegments(error);
        return;
    }
    const int temperature = static_cast<int>(roundf(value.mosto.temperature * 10));
    display.showNumberDecEx(temperature, 0x40, false, 3, 0);
    const uint8_t degree = SEG_A | SEG_B | SEG_F | SEG_G;
    display.setSegments(&degree, 1, 3);
}

void servicesTask(void*) {
    TM1637Display display(PIN_CLK, PIN_DIO);
    display.setBrightness(7);
    display.clear();
    char line[64];
    size_t used = 0;
    bool overflow = false;
    uint32_t lastDisplay = 0;
    for (;;) {
        char event[192];
        for (unsigned i = 0; i < 16 && xQueueReceive(logQueue, event, 0) == pdTRUE; ++i) Serial.println(event);
        for (unsigned i = 0; i < 64 && Serial.available(); ++i) {
            const char c = static_cast<char>(Serial.read());
            if (c == '\r') continue;
            if (c == '\n') {
                if (overflow) logEvent("[COMMAND_REJECTED] serial line too long");
                else if (used) { line[used] = '\0'; serialCommand(line); }
                used = 0;
                overflow = false;
            } else if (c == '\0') overflow = true;
            else if (used + 1 < sizeof(line)) line[used++] = c;
            else overflow = true;
        }
        SavedConfig config;
        if (xQueueReceive(saveQueue, &config, 0) == pdTRUE) saveConfiguration(config);
        const uint32_t now = millis();
        if (uint32_t(now - lastDisplay) >= 1000) {
            lastDisplay = now;
            displayTemperature(display, snapshot());
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
