#pragma once
#include <stdio.h>
#include "thermal_controller.h"

namespace thermal {
struct Telemetry {
    SensorStatus mosto, ambiente;
    Decision decision;
    float desired = 18, applied = 18, hysteresis = 0.3f;
    bool relay = false, wifi = false, mqtt = false, dryRun = true;
    uint64_t uptimeMs = 0;
    uint32_t sequence = 0, cycles = 0, rejected = 0, maxGapMs = 0;
    uint32_t wifiLosses = 0, mqttLosses = 0, droppedLogs = 0, droppedCommands = 0;
};
inline const char* jsonBool(bool value) { return value ? "true" : "false"; }
inline bool telemetryJson(const Telemetry& v, char* buffer, size_t size) {
    if (!buffer || size == 0) return false;
    char mosto[24] = "null", ambiente[24] = "null";
    if (v.mosto.valid && isfinite(v.mosto.temperature)) snprintf(mosto, sizeof(mosto), "%.3f", v.mosto.temperature);
    if (v.ambiente.valid && isfinite(v.ambiente.temperature)) snprintf(ambiente, sizeof(ambiente), "%.3f", v.ambiente.temperature);
    const int length = snprintf(buffer, size,
        "{\"mosto\":%s,\"ambiente\":%s,\"mosto_valid\":%s,\"ambiente_valid\":%s,"
        "\"mosto_fault\":\"%s\",\"ambiente_fault\":\"%s\","
        "\"setpoint_desired\":%.3f,\"setpoint_applied\":%.3f,\"setpoint\":%.3f,\"hysteresis\":%.3f,"
        "\"controller_state\":\"%s\",\"cooling_request\":%s,\"cooling_active\":%s,\"relay\":%s,\"rele\":%d,"
        "\"lockout_remaining_s\":%lu,\"wifi\":%s,\"mqtt\":%s,\"degraded\":%s,\"fault\":%s,"
        "\"uptime_s\":%llu,\"message_seq\":%lu,\"control_cycles\":%lu,\"dry_run\":%s,"
        "\"setpoint_rejections\":%lu,\"control_max_gap_ms\":%lu,\"wifi_losses\":%lu,\"mqtt_losses\":%lu,"
        "\"dropped_logs\":%lu,\"dropped_commands\":%lu}",
        mosto, ambiente, jsonBool(v.mosto.valid), jsonBool(v.ambiente.valid),
        sensorFaultName(v.mosto.fault), sensorFaultName(v.ambiente.fault), v.desired, v.applied, v.applied, v.hysteresis,
        stateName(v.decision.state), jsonBool(v.decision.coolingRequest), jsonBool(v.decision.coolingActive), jsonBool(v.relay), v.relay ? 1 : 0,
        static_cast<unsigned long>((v.decision.lockoutRemainingMs + 999) / 1000), jsonBool(v.wifi), jsonBool(v.mqtt), jsonBool(v.decision.degraded),
        !v.decision.fault ? "null" : strcmp(v.decision.fault, "internal_error") == 0 ? "\"internal_error\"" : "\"mosto_sensor\"",
        static_cast<unsigned long long>(v.uptimeMs / 1000), static_cast<unsigned long>(v.sequence), static_cast<unsigned long>(v.cycles), jsonBool(v.dryRun),
        static_cast<unsigned long>(v.rejected), static_cast<unsigned long>(v.maxGapMs), static_cast<unsigned long>(v.wifiLosses), static_cast<unsigned long>(v.mqttLosses),
        static_cast<unsigned long>(v.droppedLogs), static_cast<unsigned long>(v.droppedCommands));
    if (length < 0 || static_cast<size_t>(length) >= size) { buffer[0] = '\0'; return false; }
    return true;
}
} // namespace thermal
