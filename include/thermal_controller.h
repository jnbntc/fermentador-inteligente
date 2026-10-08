#pragma once
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include "cooling_guard.h"

namespace thermal {
constexpr uint32_t MIN_OFF_MS = 300000;
constexpr uint32_t SENSOR_STALE_MS = 5000;
constexpr unsigned VALID_READINGS = 3;

enum class State : uint8_t { BOOT_HOLD, IDLE, COOLING, COMPRESSOR_LOCKOUT, SENSOR_FAULT, MAINTENANCE };
inline const char* stateName(State s) {
    switch (s) {
        case State::BOOT_HOLD: return "BOOT_HOLD";
        case State::IDLE: return "IDLE";
        case State::COOLING: return "COOLING";
        case State::COMPRESSOR_LOCKOUT: return "COMPRESSOR_LOCKOUT";
        case State::SENSOR_FAULT: return "SENSOR_FAULT";
        case State::MAINTENANCE: return "MAINTENANCE";
    }
    return "UNKNOWN";
}
enum class SensorFault : uint8_t { NONE, VALIDATING, DISCONNECTED, POWER_ON_85, NONFINITE, RANGE, STALE };
inline const char* sensorFaultName(SensorFault f) {
    switch (f) {
        case SensorFault::NONE: return "none";
        case SensorFault::VALIDATING: return "validating";
        case SensorFault::DISCONNECTED: return "disconnected";
        case SensorFault::POWER_ON_85: return "power_on_85";
        case SensorFault::NONFINITE: return "nonfinite";
        case SensorFault::RANGE: return "range";
        case SensorFault::STALE: return "stale";
    }
    return "unknown";
}
struct SensorStatus {
    float temperature = NAN;
    bool valid = false;
    SensorFault fault = SensorFault::STALE;
};

// Los límites son del proceso actual, no el rango completo del DS18B20.
class SensorValidator {
public:
    SensorValidator(float minimum, float maximum) : minimum_(minimum), maximum_(maximum) {}
    void sample(float value, uint32_t now, bool responded = true) {
        const bool duplicate = hasReading_ && now == lastReading_;
        if (hasReading_ && uint32_t(now - lastReading_) > SENSOR_STALE_MS) consecutive_ = 0;
        status_.temperature = value;
        hasReading_ = true;
        lastReading_ = now;
        SensorFault reason = SensorFault::NONE;
        if (!responded || value == -127.0f) reason = SensorFault::DISCONNECTED;
        else if (!isfinite(value)) reason = SensorFault::NONFINITE;
        else if (value == 85.0f) reason = SensorFault::POWER_ON_85;
        else if (value < minimum_ || value > maximum_) reason = SensorFault::RANGE;
        if (reason != SensorFault::NONE) {
            consecutive_ = 0;
            status_.valid = false;
            status_.fault = reason;
            return;
        }
        if (duplicate) return; // Una conversión válida no cuenta varias veces.
        if (consecutive_ < VALID_READINGS) ++consecutive_;
        status_.valid = consecutive_ >= VALID_READINGS;
        status_.fault = status_.valid ? SensorFault::NONE : SensorFault::VALIDATING;
    }
    SensorStatus status(uint32_t now) {
        if (!hasReading_ || uint32_t(now - lastReading_) > SENSOR_STALE_MS) {
            consecutive_ = 0;
            status_.valid = false;
            status_.fault = SensorFault::STALE;
        }
        return status_;
    }
private:
    float minimum_, maximum_;
    SensorStatus status_;
    uint32_t lastReading_ = 0;
    unsigned consecutive_ = 0;
    bool hasReading_ = false;
};

inline bool validSetpoint(float value) { return isfinite(value) && value > 0 && value < 30; }
inline bool validHysteresis(float value) { return isfinite(value) && value >= 0.05f && value <= 2.0f; }

// Consume el payload entero. No acepta prefijos numéricos, NUL ni basura final.
inline bool parseNumber(const char* bytes, size_t length, float& value) {
    if (!bytes || length == 0 || length > 32) return false;
    char text[33];
    for (size_t i = 0; i < length; ++i) {
        if (bytes[i] == '\0') return false;
        text[i] = bytes[i];
    }
    text[length] = '\0';
    char* end = nullptr;
    errno = 0;
    float candidate = strtof(text, &end);
    if (end == text || errno == ERANGE || !isfinite(candidate)) return false;
    while (*end && isspace(static_cast<unsigned char>(*end))) ++end;
    if (*end) return false;
    value = candidate;
    return true;
}

struct Decision {
    State state = State::BOOT_HOLD;
    bool coolingRequest = false;
    bool coolingActive = false;
    bool degraded = true;
    uint32_t lockoutRemainingMs = MIN_OFF_MS;
    const char* fault = nullptr;
};
inline bool safeCoolingCommand(const Decision& d) {
    return d.state == State::COOLING && d.coolingRequest && d.coolingActive && d.fault == nullptr;
}

// Sin Arduino, red, reloj UTC, display ni salida física.
class Controller {
public:
    void boot(uint32_t now) {
        guard_.reset(now);
        bootAt_ = now;
        lastTick_ = now;
        uptimeMs_ = 0;
        desired_ = applied_;
        rejected_ = 0;
        bootHolding_ = true;
        request_ = false;
        maintenance_ = false;
        internalFault_ = false;
        decision_ = Decision{};
    }
    bool setpoint(float value) {
        if (isfinite(value)) desired_ = value;
        if (!validSetpoint(value)) { ++rejected_; return false; }
        applied_ = value;
        return true;
    }
    bool hysteresis(float value) {
        if (!validHysteresis(value)) return false;
        hysteresis_ = value;
        return true;
    }
    void maintenance(bool enabled) { maintenance_ = enabled; }
    void fail() { internalFault_ = true; }
    Decision tick(uint32_t now, SensorStatus mosto, SensorStatus ambiente, bool externalMaintenance = false) {
        uptimeMs_ += uint32_t(now - lastTick_);
        lastTick_ = now;
        if (static_cast<unsigned>(decision_.state) > static_cast<unsigned>(State::MAINTENANCE)) internalFault_ = true;
        if (uint32_t(now - bootAt_) >= MIN_OFF_MS) bootHolding_ = false;
        decision_.degraded = !ambiente.valid || !isfinite(ambiente.temperature);
        decision_.fault = nullptr;
        const bool validMosto = mosto.valid && isfinite(mosto.temperature) && mosto.temperature >= -5 && mosto.temperature <= 40;
        if (internalFault_) {
            stop(now);
            decision_.state = State::SENSOR_FAULT;
            decision_.fault = "internal_error";
        } else if (maintenance_ || externalMaintenance) {
            stop(now);
            decision_.state = State::MAINTENANCE;
        } else if (!validMosto) {
            stop(now);
            decision_.state = State::SENSOR_FAULT;
            decision_.fault = "mosto_sensor";
        } else {
            if (mosto.temperature > applied_ + hysteresis_) request_ = true;
            else if (mosto.temperature <= applied_ - hysteresis_) request_ = false;
            if (bootHolding_) {
                guard_.forceOff(now);
                decision_.state = State::BOOT_HOLD;
            } else if (!request_) {
                guard_.forceOff(now);
                decision_.state = State::IDLE;
            } else if (guard_.requestOn(now)) {
                decision_.state = State::COOLING;
            } else {
                decision_.state = State::COMPRESSOR_LOCKOUT;
            }
        }
        decision_.coolingRequest = request_;
        decision_.coolingActive = guard_.enabled();
        decision_.lockoutRemainingMs = guard_.remainingMs(now);
        return decision_;
    }
    float desired() const { return desired_; }
    float applied() const { return applied_; }
    float hysteresis() const { return hysteresis_; }
    uint32_t rejected() const { return rejected_; }
    uint64_t uptimeMs() const { return uptimeMs_; }
private:
    void stop(uint32_t now) { guard_.forceOff(now); request_ = false; }
    CoolingGuard guard_{MIN_OFF_MS};
    Decision decision_;
    uint32_t bootAt_ = 0, lastTick_ = 0, rejected_ = 0;
    uint64_t uptimeMs_ = 0;
    float desired_ = 18, applied_ = 18, hysteresis_ = 0.3f;
    bool request_ = false, maintenance_ = false, internalFault_ = false, bootHolding_ = true;
};
} // namespace thermal
