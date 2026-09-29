# Fermentador Edge

Firmware for a fermentation temperature controller based on ESP32.

## Description

This project implements an embedded system that:

- measures temperatures with DS18B20 sensors,
- controls a cooling relay,
- displays the temperature on a TM1637 display,
- publishes telemetry over MQTT,
- supports OTA updates.

## Expected Hardware

- ESP32 DevKit v1
- 2 DS18B20 sensors (must and ambient)
- Relay for compressor/cooling
- 4-digit TM1637 display
- OneWire wiring on GPIO 4

## Main Features

- Thermal control with configurable hysteresis
- Safety protection for sensor failures
- Automatic MQTT reconnection
- Publication of status to `birra/telemetria`
- Subscription to `birra/setpoint` to adjust the setpoint
- OTA with hostname `esp32-fermentador`

## Dependencies

The project uses PlatformIO with the following libraries:

- DallasTemperature
- OneWire
- PubSubClient
- TM1637Display

The build configuration is defined in `platformio.ini`.

## Development environment

This repository intentionally does not define its own Dev Container. Embedded development uses the shared `iot-dev` Distrobox workspace from `jnbntc/distrobox-stack`, which provides the canonical PlatformIO Core, Python, USB tooling and board toolchains.

CLI workflow:

```sh
distrobox enter iot-dev
cd ~/Proyectos/fermentador-edge
pio run -e esp32doit-devkit-v1
```

VS Code workflow:

1. Start `iot-dev` if necessary: `podman start iot-dev`.
2. Run **Dev Containers: Attach to Running Container...**.
3. Select `iot-dev`.
4. Open this project folder from the shared home directory.
5. Use the PlatformIO extension configured to use the existing PlatformIO Core inside `iot-dev`.

The project itself keeps hardware, framework, libraries and build options in `platformio.ini`; editor/container configuration is intentionally kept outside this repository.

## Requirements

- the shared `iot-dev` workspace
- the target ESP32 hardware
- local `secrets.ini`

## Quick Setup

1. Adjust sensitive values in `secrets.ini`.
2. Build the firmware:

   ```sh
   pio run -e esp32doit-devkit-v1
   ```

3. Upload the firmware to the board:

   ```sh
   pio run -e esp32doit-devkit-v1 -t upload
   ```

4. To monitor the serial output:

   ```sh
   pio device monitor -e esp32doit-devkit-v1
   ```

## Important Notes

- `secrets.ini` is used as extra PlatformIO configuration and contains network and MQTT credentials.
- Do not upload real secrets to the repository.
- The firmware is prepared to work with an MQTT broker on port 1883.

## Project Structure

- `src/main.cpp` — main firmware logic
- `platformio.ini` — PlatformIO configuration
- `secrets.ini` — local credentials and sensitive configuration
- `include/` — local libraries or headers
- `lib/` — custom libraries
- `test/` — tests and validations
