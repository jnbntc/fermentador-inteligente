#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "thermal_controller.h"
#include "cooling_output.h"
#include "telemetry.h"
using namespace thermal;

static SensorStatus valid(float t) {
    SensorStatus status;
    status.temperature = t;
    status.valid = true;
    status.fault = SensorFault::NONE;
    return status;
}
static SensorStatus invalid() { return SensorStatus{}; }
static unsigned cases = 0;
static void passed(const char* name) { ++cases; printf("PASS %s\n", name); }
struct FakePin {
    bool high = false;
    unsigned lowWrites = 0;
    void prepareOff() { high = true; }
    void writeHigh(bool value) { high = value; if (!value) ++lowWrites; }
};
int main() {
    Controller c;
    c.boot(0);
    auto d = c.tick(300000, valid(18), valid(22));
    assert(d.state == State::IDLE && !d.coolingRequest && !d.coolingActive);
    passed("A idle at setpoint");

    d = c.tick(300020, valid(18.4f), valid(22));
    assert(d.state == State::COOLING && d.coolingRequest && d.coolingActive);
    passed("B cooling above upper band");
    d = c.tick(300040, valid(18), valid(22));
    assert(d.coolingActive);
    d = c.tick(300060, valid(17.6f), valid(22));
    assert(d.state == State::IDLE && !d.coolingActive);
    passed("C hysteresis retains then stops cooling");
    d = c.tick(300080, valid(19), valid(22));
    assert(d.state == State::COMPRESSOR_LOCKOUT && d.coolingRequest && !d.coolingActive);
    d = c.tick(600059, valid(19), valid(22));
    assert(!d.coolingActive && d.lockoutRemainingMs == 1);
    d = c.tick(600060, valid(19), valid(22));
    assert(d.coolingActive);
    passed("D off interval and exact boundary");

    c.boot(700000);
    const uint32_t bootTimes[] = {0u, 1000u, 299999u};
    for (uint32_t elapsed : bootTimes) {
        d = c.tick(700000 + elapsed, valid(25), valid(22));
        assert(d.state == State::BOOT_HOLD && !d.coolingActive);
    }
    assert(c.tick(1000000, valid(25), valid(22)).coolingActive);
    passed("E reboot hold after previously running");

    d = c.tick(1000020, invalid(), valid(22));
    assert(d.state == State::SENSOR_FAULT && !d.coolingActive && strcmp(d.fault, "mosto_sensor") == 0);
    d = c.tick(1000040, valid(25), valid(22));
    assert(d.state == State::COMPRESSOR_LOCKOUT && !d.coolingActive);
    assert(c.tick(1300020, valid(25), valid(22)).coolingActive);
    passed("F mosto fault immediately stops and recovery keeps guard");
    d = c.tick(1300040, valid(25), invalid());
    assert(d.state == State::COOLING && d.coolingActive && d.degraded);
    passed("G ambient failure degrades without disabling mosto control");

    const float badSetpoints[] = {0.0f, 30.0f, -1.0f, INFINITY, NAN};
    for (float value : badSetpoints) {
        assert(!c.setpoint(value));
        assert(c.applied() == 18);
    }
    assert(c.desired() == -1);
    assert(c.setpoint(19));
    assert(c.desired() == 19 && c.applied() == 19);
    passed("H invalid setpoint rejected with applied unchanged");

    // No red ni mocks MQTT: avanzar el controlador desconectado durante 2 h.
    c.boot(0);
    for (uint32_t t = 0; t < 7200000; t += 20) {
        d = c.tick(t, valid(t % 600000 < 350000 ? 25 : 17), valid(22));
        if (t < MIN_OFF_MS) assert(!d.coolingActive);
        assert(!d.coolingActive || safeCoolingCommand(d));
    }
    assert(c.uptimeMs() == 7199980);
    passed("I local operation for two hours without any transport");

    SensorValidator mosto(-5, 40);
    mosto.sample(85, 0);
    assert(!mosto.status(0).valid && mosto.status(0).fault == SensorFault::POWER_ON_85);
    mosto.sample(18, 1000);
    assert(!mosto.status(1000).valid);
    mosto.sample(18, 2000);
    assert(!mosto.status(2000).valid);
    mosto.sample(18, 3000);
    assert(mosto.status(3000).valid);
    passed("J isolated 85 and three consecutive fresh readings");

    const float badReadings[] = {-127.0f, NAN, INFINITY, -6.0f, 41.0f, 85.0f};
    for (float value : badReadings) {
        mosto.sample(value, 4000);
        assert(!mosto.status(4000).valid);
        mosto.sample(18, 5000);
        mosto.sample(18, 6000);
        assert(!mosto.status(6000).valid);
        mosto.sample(18, 7000);
        assert(mosto.status(7000).valid);
    }
    mosto.sample(18, 8000, false);
    assert(!mosto.status(8000).valid);
    const uint32_t recoveryTimes[] = {9000u, 10000u, 11000u};
    for (uint32_t t : recoveryTimes) mosto.sample(18, t);
    assert(mosto.status(16000).valid);
    assert(!mosto.status(16001).valid);
    mosto.sample(18, 16002);
    assert(!mosto.status(16002).valid);
    SensorValidator duplicates(-5, 40);
    duplicates.sample(18, 0); duplicates.sample(18, 0); duplicates.sample(18, 0);
    assert(!duplicates.status(0).valid);
    duplicates.sample(18, 1000); duplicates.sample(18, 2000);
    assert(duplicates.status(2000).valid);
    duplicates.sample(NAN, 2000);
    assert(!duplicates.status(2000).valid);
    duplicates.sample(18, 10000);
    assert(!duplicates.status(10000).valid);
    passed("K invalid samples, duplicate conversions, missing response, staleness and recovery");

    c.boot(0);
    assert(c.tick(300000, valid(25), valid(22)).coolingActive);
    c.maintenance(true);
    d = c.tick(300020, valid(25), valid(22));
    assert(d.state == State::MAINTENANCE && !d.coolingActive);
    c.maintenance(false);
    d = c.tick(300040, valid(25), valid(22));
    assert(d.state == State::COMPRESSOR_LOCKOUT);
    c.fail();
    d = c.tick(900000, valid(25), valid(22));
    assert(d.state == State::SENSOR_FAULT && !d.coolingActive && strcmp(d.fault, "internal_error") == 0);
    assert(!c.tick(1200000, valid(25), valid(22)).coolingActive);
    passed("L maintenance, recovery guard and latched internal error");

    c.boot(UINT32_MAX - 100000);
    assert(!c.tick(199998, valid(25), valid(22)).coolingActive);
    assert(c.tick(199999, valid(25), valid(22)).coolingActive);
    mosto.sample(18, UINT32_MAX - 2000);
    mosto.sample(18, UINT32_MAX - 1000);
    mosto.sample(18, UINT32_MAX);
    assert(mosto.status(4000).valid);
    assert(!mosto.status(5001).valid);
    passed("M millis wrap for boot and sensor freshness");

    float number = 99;
    const char* badPayloads[] = {"18junk", "nan", "inf", "", "   ", "1e999", "18 19", "--18"};
    for (const char* text : badPayloads) assert(!parseNumber(text, strlen(text), number));
    const char embedded[] = {'1','8','\0','9'};
    assert(!parseNumber(embedded, sizeof(embedded), number));
    assert(parseNumber(" 18.5\r\n", 7, number) && number == 18.5f);
    assert(!c.hysteresis(0) && !c.hysteresis(NAN) && !c.hysteresis(2.1f));
    assert(c.hysteresis(0.5f));
    passed("N strict payload parser and bounded configurable hysteresis");

    FakePin pin, dryPin;
    CoolingOutput<FakePin> output(pin, false), dryOutput(dryPin, true);
    output.begin(); dryOutput.begin();
    assert(pin.high && dryPin.high);
    c.boot(0);
    d = c.tick(300000, valid(25), valid(22));
    output.set(d); dryOutput.set(d);
    assert(!pin.high && output.active());
    assert(dryPin.high && !dryOutput.active() && dryPin.lowWrites == 0);
    const State offStates[] = {State::BOOT_HOLD, State::IDLE, State::COMPRESSOR_LOCKOUT, State::SENSOR_FAULT, State::MAINTENANCE, static_cast<State>(255)};
    for (State state : offStates) {
        d.state = state;
        output.set(d); dryOutput.set(d);
        assert(pin.high && dryPin.high && !output.active());
    }
    passed("O active-low output, all OFF states, unknown state and DRY_RUN");

    Telemetry v;
    v.mosto = valid(18.4f); v.ambiente = invalid();
    v.decision = c.tick(300020, v.mosto, v.ambiente);
    v.mqttLosses = 1; v.sequence = 42; v.cycles = 123;
    char json[1200], shortBuffer[8];
    assert(telemetryJson(v, json, sizeof(json)));
    assert(strstr(json, "\"ambiente\":null") && strstr(json, "\"message_seq\":42"));
    assert(!telemetryJson(v, shortBuffer, sizeof(shortBuffer)) && shortBuffer[0] == '\0');
    assert(!telemetryJson(v, nullptr, 0));
    printf("JSON %s\n", json);
    v.mosto = invalid();
    v.decision = c.tick(300040, v.mosto, v.ambiente);
    assert(telemetryJson(v, json, sizeof(json)));
    printf("JSON %s\n", json);
    passed("P observable telemetry and bounded buffer");
    printf("%u scenarios passed\n", cases);
}
