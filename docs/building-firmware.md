# Building the Khan-Nomad firmware

How to compile `firmware/JcorpNomadProject` yourself with **arduino-cli**
(no Arduino IDE needed) and flash it to the Waveshare ESP32-S3-LCD-1.47.

## One-time setup (Windows)

```bash
winget install --id ArduinoSA.CLI --exact
arduino-cli config init
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32@3.3.3
arduino-cli lib install "ArduinoJson@7.3.0" "Async TCP@3.4.7" "ESP Async WebServer@3.7.1" "lvgl@8.4.0" "SdFat@2.3.0"
```

The ESP32 core is a large download (compilers and tools, roughly 1-2 GB).

LVGL needs its config file next to the libraries. Copy
`firmware/JcorpNomadProject/lv_conf.h` into your Arduino `libraries` folder
(`arduino-cli config get directories.user`, then `libraries/`), beside the
`lvgl` folder.

## Board settings

These are the original Nomad settings (from the upstream README history):

| Setting | Value | arduino-cli option |
|---|---|---|
| Board | ESP32S3 Dev Module | `esp32:esp32:esp32s3` |
| USB CDC On Boot | Enabled | `CDCOnBoot=cdc` |
| Flash Size | 16MB (128Mb) | `FlashSize=16M` |
| Partition Scheme | 16MB Flash (3MB APP/9.9MB FATFS) | `PartitionScheme=app3M_fat9M_16MB` |
| PSRAM | OPI PSRAM | `PSRAM=opi` |
| USB Mode | USB-OTG (TinyUSB) | `USBMode=default` |
| Upload Speed | 921600 | `UploadSpeed=921600` |

## Compile

From the repo root:

```bash
arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi,USBMode=default,UploadSpeed=921600" --output-dir build firmware/JcorpNomadProject
```

The first build takes several minutes (LVGL is big); later builds are faster.
`build/` gets `JcorpNomadProject.ino.merged.bin`, a single image with the
bootloader, partition table and app.

For the USB-C board (ESP32-S3-LCD-1.47B) add `--build-property "compiler.cpp.extra_flags=-DBOARD_USB_C=1"`
so the backlight uses GPIO46.

## Flash

Plug the board in, find its port with `arduino-cli board list`, then:

```bash
arduino-cli upload -p COM5 --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi,USBMode=default,UploadSpeed=921600" --input-dir build firmware/JcorpNomadProject
```

Replace `COM5` with your port. If the board isn't detected, hold **BOOT**,
tap **RESET**, release **BOOT**, and try again.

You can also flash `JcorpNomadProject.ino.merged.bin` at address `0x0` with
any ESP32 web flasher (for example <https://espressif.github.io/esptool-js/>).

## What Khan-Nomad changes in the firmware

- Default WiFi name `Khan-Nomad` (was `Jcorp_Nomad`). A name saved earlier in
  the admin settings still wins.
- The LCD shows the steppe yurt logo.
- TVs see the DLNA server as `Khan-Nomad`.
- The web address stays `http://nomad.local` (and `192.168.4.1`).
