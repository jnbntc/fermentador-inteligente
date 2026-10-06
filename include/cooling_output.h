#pragma once
#include "thermal_controller.h"

// El escritor encapsula GPIO. En DRY_RUN siempre recibe HIGH (OFF).
template <typename PinWriter>
class CoolingOutput {
public:
    CoolingOutput(PinWriter& pin, bool dryRun) : pin_(pin), dryRun_(dryRun) {}
    void begin() { pin_.prepareOff(); physical_ = false; }
    void set(const thermal::Decision& decision) {
        physical_ = !dryRun_ && thermal::safeCoolingCommand(decision);
        pin_.writeHigh(!physical_);
    }
    bool active() const { return physical_; }
private:
    PinWriter& pin_;
    bool dryRun_, physical_ = false;
};
