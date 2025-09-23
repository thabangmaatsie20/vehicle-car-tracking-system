# ESP32-CAM (PlatformIO) – Face Recognition skeleton

## Structure
- `esp32cam-pio/platformio.ini`: board/env config, flags
- `esp32cam-pio/src/main.cpp`: sketch with feature flags
- `esp32cam-pio/include/secrets.h`: put credentials here

## Setup
1. Install PlatformIO (VS Code extension or `pipx install platformio`).
2. Open the `esp32cam-pio` folder as the project.
3. Edit `include/secrets.h` with your Wi‑Fi, ThingSpeak key, and Gmail app password.

## Build/Upload
```
pio run -d esp32cam-pio
pio run -d esp32cam-pio -t upload
pio device monitor -d esp32cam-pio -b 115200
```

## Feature flags
Toggle compile-time features in `platformio.ini` (or change defines in `src/main.cpp`):
- `FEAT_HTTP` – ThingSpeak updates
- `FEAT_EMAIL` – Gmail SMTP alerts
- `FEAT_LCD` – I2C LCD
- `FEAT_SD` – SD/face loading

Disabling heavy features speeds up compiles during iteration.

## Notes
- The ESP32 core bundles `esp32-camera` and `esp-face`. Ensure PSRAM is enabled.
- If you hit flash size issues, keep `huge_app.csv` partition and disable features.
