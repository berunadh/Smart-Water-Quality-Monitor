# Arduino IDE Setup & Firmware Upload Guide (macOS Apple Silicon)

This guide provides step-by-step instructions for opening, configuring, compiling, and flashing the **Smart Water Quality Monitor** firmware using **Arduino IDE 2.x** on a **macOS Apple Silicon (M-series) MacBook**.

---

## 1. System Requirements & Prerequisites

- **Machine**: Apple Silicon Mac (M1/M2/M3/M4/M5) running macOS.
- **IDE**: Arduino IDE 2.x (installed in `/Applications/Arduino IDE.app`).
- **USB Cable**: Good quality USB-C to Micro-USB (or USB-C to USB-A adapter) that supports **data transmission** (not power-only charging cables).
- **USB-UART Driver**: macOS includes built-in drivers for CP2102 and FTDI chips. If your ESP32 board uses the CH340 chip, ensure the macOS CH34x driver is installed.

---

## 2. Arduino IDE Board Package Installation

1. Launch **Arduino IDE**.
2. Open **Settings** (or press `Cmd + ,`).
3. In **Additional boards manager URLs**, add:
   ```text
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
4. Click **OK**.
5. Open the **Boards Manager** icon on the left sidebar (or press `Cmd + Shift + B`).
6. Type `esp32` in the search box.
7. Locate **esp32 by Espressif Systems** and verify version **3.x.x** is installed.

---

## 3. Required Library Verification

Open the **Library Manager** (icon on left sidebar or press `Cmd + Shift + I`) and ensure the following libraries are installed:

| Library Name | Author | Purpose | Status in Workspace |
| :--- | :--- | :--- | :--- |
| **Adafruit SSD1306** | Adafruit | OLED display driver | ✅ Installed |
| **Adafruit GFX Library** | Adafruit | Core 2D graphics primitive engine | ✅ Installed |
| **Adafruit BusIO** | Adafruit | I2C / SPI bus communication helper | ✅ Installed |
| **WiFi** | Espressif Systems | Built-in with ESP32 core | ✅ Included |
| **HTTPClient** | Espressif Systems | Built-in with ESP32 core | ✅ Included |
| **Wire** | Espressif Systems | Built-in I2C hardware core | ✅ Included |

---

## 4. Board Settings Configuration

Under the **Tools** menu in Arduino IDE, select the following options:

- **Board**: `esp32` $\rightarrow$ **ESP32 Dev Module**
- **Upload Speed**: `115200` (or `921600` for faster uploads)
- **CPU Frequency**: `240MHz (WiFi/BT)`
- **Flash Frequency**: `80MHz`
- **Flash Mode**: `QIO`
- **Flash Size**: `4MB (32Mb)`
- **Partition Scheme**: `Default 4MB with spiffs (1.2MB APP / 1.5MB SPIFFS)`
- **Core Debug Level**: `None` (or `Info` for debugging)
- **Port**: Select `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial*`

---

## 5. Firmware Configuration & Secrets

Before flashing, enter your local network credentials:

1. Navigate to:
   ```bash
   firmware/water_monitor/secrets.h
   ```
2. Populate your Wi-Fi credentials and optional ThingSpeak credentials:
   ```cpp
   #define WIFI_SSID               "YourApartmentWiFi"
   #define WIFI_PASSWORD           "YourWiFiPassword"
   #define THINGSPEAK_CHANNEL_ID   1234567UL
   #define THINGSPEAK_WRITE_API_KEY "YOUR_THINGSPEAK_WRITE_KEY"
   ```
3. *Note*: `secrets.h` is ignored by Git, ensuring your credentials are never exposed in version control.

---

## 6. Flashing the Firmware

1. Plug the ESP32 into your MacBook.
2. In Arduino IDE, click the **Verify** checkmark button (or press `Cmd + R`) to compile.
3. Click the **Upload** arrow button (or press `Cmd + U`).
4. **Bootloader Tip**:
   - If the IDE output window displays `Connecting........_____.....`:
   - Press and hold the **BOOT (or IO0)** button on the ESP32 board for 2 seconds until the writing progress percentage (`Writing at 0x00010000... (10 %)`) appears, then release the button.
5. Once upload completes, open the **Serial Monitor** (`Cmd + Shift + M`).
6. Set baud rate to **115200 baud** and line ending to **Newline**.
7. Press the **EN / RST** button on the ESP32 to restart and view the bootup banner.

---

## 7. Fast Terminal Build (Automated Verification)

You can also compile the firmware directly from your terminal on macOS without opening the Arduino IDE GUI:

```bash
cd /Users/berunadh/Desktop/projects/O3_S1_TBP/Smart-Water-Quality-Monitor
./scripts/compile_firmware.sh
```
This script automatically invokes the Arduino CLI bundled with Arduino IDE and compiles the sketch with 0 errors.
