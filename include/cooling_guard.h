#pragma once
#include <stdint.h>

// Todas las causas de apagado comparten el mismo intervalo de protección.
class CoolingGuard {
public:
    explicit CoolingGuard(uint32_t minOffMs) : minOffMs_(minOffMs) {}

    void reset(uint32_t now) {
        enabled_ = false;
        lastOff_ = now;
    }

    void forceOff(uint32_t now) {
        if (enabled_) lastOff_ = now;
        enabled_ = false;
    }

    bool requestOn(uint32_t now) {
        if (enabled_ || uint32_t(now - lastOff_) >= minOffMs_) enabled_ = true;
        return enabled_;
    }

    bool enabled() const { return enabled_; }

    uint32_t remainingMs(uint32_t now) const {
        if (enabled_) return 0;
        const uint32_t elapsed = uint32_t(now - lastOff_);
        return elapsed >= minOffMs_ ? 0 : minOffMs_ - elapsed;
    }

private:
    uint32_t minOffMs_;
    uint32_t lastOff_ = 0;
    bool enabled_ = false;
};
