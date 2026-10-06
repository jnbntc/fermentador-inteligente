#include "sensor_reader.h"
#include "runtime.h"

void SensorReader::begin() {
    sensors_.begin();
    parasite_ = sensors_.isParasitePowerMode();
    sensors_.setResolution(ROM_MOSTO, 11);
    sensors_.setResolution(ROM_AMBIENTE, 11);
    sensors_.setWaitForConversion(false);
    if (parasite_) logEvent("[SENSOR_FAULT] parasite power unsupported; use three-wire power");
}

void SensorReader::poll(uint32_t now) {
    // Conversiones a 11 bits (375 ms). Timeout limitado: no esperar en un bucle.
    if (!conversion_) {
        if (first_ || uint32_t(now - nextSampleAt_) >= 1000) {
            first_ = false;
            nextSampleAt_ = now;
            sensors_.requestTemperatures();
            requestedAt_ = now;
            conversion_ = true;
        }
        return;
    }
    if (uint32_t(now - requestedAt_) < 375) return;
    bool complete = !parasite_ && sensors_.isConversionComplete();
    if (!complete && uint32_t(now - requestedAt_) < 750) return;
    float m = complete ? sensors_.getTempC(ROM_MOSTO) : NAN;
    float a = complete ? sensors_.getTempC(ROM_AMBIENTE) : NAN;
#if DRY_RUN
    if (simMosto_) m = simulatedMosto_;
    if (simAmbiente_) a = simulatedAmbiente_;
    mosto_.sample(m, now, simMosto_ || complete);
    ambiente_.sample(a, now, simAmbiente_ || complete);
#else
    mosto_.sample(m, now, complete);
    ambiente_.sample(a, now, complete);
#endif
    conversion_ = false;
}

void SensorReader::diagnose() {
    // Buscar nuevamente permite descubrir sensores reconectados y ROM nuevas.
    uint8_t rom[8];
    wire_.reset_search();
    unsigned count = 0;
    while (count < 8 && wire_.search(rom)) {
        ++count;
        float temp = sensors_.getTempC(rom);
        bool crc = OneWire::crc8(rom, 7) == rom[7];
        thermal::SensorValidator diagnostic(-20, 60);
        diagnostic.sample(temp, millis(), crc && rom[0] == 0x28);
        const auto status = diagnostic.status(millis());
        logEvent("[ROM] %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X T=%.2f reason=%s role=%s",
            rom[0], rom[1], rom[2], rom[3], rom[4], rom[5], rom[6], rom[7], temp,
            thermal::sensorFaultName(status.fault),
            memcmp(rom, ROM_MOSTO, 8) == 0 ? "MOSTO" : memcmp(rom, ROM_AMBIENTE, 8) == 0 ? "AMBIENTE" : "UNASSIGNED");
    }
    logEvent("[ROM] found=%u (max 8); one reading does not authorize control", count);
}
#if DRY_RUN
void SensorReader::simulate(bool mosto, float value) {
    if (mosto) { simMosto_ = true; simulatedMosto_ = value; }
    else { simAmbiente_ = true; simulatedAmbiente_ = value; }
}
#endif
