#pragma once
#include <OneWire.h>
#include <DallasTemperature.h>
#include "hardware_config.h"
#include "thermal_controller.h"

// Solo la tarea de control es dueña del bus y los validadores.
class SensorReader {
public:
    SensorReader() : wire_(PIN_ONE_WIRE), sensors_(&wire_) {}
    void begin();
    void poll(uint32_t now);
    void diagnose();
    thermal::SensorStatus mosto(uint32_t now) { return mosto_.status(now); }
    thermal::SensorStatus ambiente(uint32_t now) { return ambiente_.status(now); }
#if DRY_RUN
    void simulate(bool mosto, float value);
    void clearSimulation() { simMosto_ = simAmbiente_ = false; }
#endif
private:
    OneWire wire_;
    DallasTemperature sensors_;
    thermal::SensorValidator mosto_{-5, 40}, ambiente_{-20, 60};
    uint32_t requestedAt_ = 0, nextSampleAt_ = 0;
    bool conversion_ = false, first_ = true, parasite_ = false;
#if DRY_RUN
    bool simMosto_ = false, simAmbiente_ = false;
    float simulatedMosto_ = NAN, simulatedAmbiente_ = NAN;
#endif
};
