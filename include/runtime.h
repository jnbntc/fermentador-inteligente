#pragma once
#include <Arduino.h>
#include "thermal_controller.h"
#include "hardware_config.h"

enum class CommandType : uint8_t { SETPOINT, REJECT_SETPOINT, HYSTERESIS, MAINTENANCE, DIAGNOSE, SIM_MOSTO, SIM_AMBIENTE, SIM_CLEAR };
struct Command {
    CommandType type;
    float value;
    bool remote;
    Command(CommandType t = CommandType::DIAGNOSE, float v = 0, bool r = false) : type(t), value(v), remote(r) {}
};
struct Snapshot {
    thermal::SensorStatus mosto, ambiente;
    thermal::Decision decision;
    float desired = 18, applied = 18, hysteresis = 0.3f;
    bool relay = false;
    uint64_t uptimeMs = 0;
    uint32_t cycles = 0, rejected = 0, maxGapMs = 0;
};
struct TransportStatus {
    bool wifi = false, mqtt = false;
    uint32_t wifiLosses = 0, mqttLosses = 0, droppedLogs = 0, droppedCommands = 0;
};
struct SavedConfig { float setpoint, hysteresis; };

extern QueueHandle_t commands, logQueue, saveQueue;
Snapshot snapshot();
void updateSnapshot(const Snapshot& value);
TransportStatus transportStatus();
void updateTransport(bool wifi, bool mqtt);
bool otaMaintenance();
void latchOtaMaintenance();
bool enqueue(Command command);
void logEvent(const char* format, ...);
void printStatus(const Snapshot& value);
void servicesTask(void*);
void networkTask(void*);
