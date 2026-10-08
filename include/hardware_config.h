#pragma once
#include <stdint.h>
#ifndef DRY_RUN
#define DRY_RUN 1
#endif
#ifndef ENABLE_OTA
#define ENABLE_OTA 0
#endif
#ifndef ACCEPT_MQTT_SETPOINTS
#define ACCEPT_MQTT_SETPOINTS 0
#endif
constexpr int PIN_ONE_WIRE = 4;
constexpr int PIN_RELE_FRIO = 26;
constexpr int PIN_CLK = 18;
constexpr int PIN_DIO = 19;
// Conservar el mapeo existente; verificarlo con ROM antes de conectar el compresor.
static const uint8_t ROM_MOSTO[8] = {0x28, 0xFF, 0xB0, 0x96, 0x51, 0x16, 0x04, 0x18};
static const uint8_t ROM_AMBIENTE[8] = {0x28, 0xFF, 0x6A, 0x47, 0x55, 0x16, 0x03, 0x68};
