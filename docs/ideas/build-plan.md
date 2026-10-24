# Two-device build plan

Tracking the build of both devices in this fork.

## 1. Main Nomad

**Board:** Waveshare ESP32-S3-LCD-1.47 (USB-A version, SKU 28317, part number
`ESP32-S3-LCD-1.47`). Ordered 2026-10-21. This is the board Nomad is designed
for: built-in 1.47" screen, microSD slot and RGB LED, so no wiring is needed.

### Software (done before the board arrives)

- [x] Fake Nomad on the laptop to preview the interface ([tools/fake-nomad](../../tools/fake-nomad/README.md))
- [x] Khan-Nomad name and steppe yurt logo, favicon and phone icon
- [x] Steppe Night theme as the default (light and dark)
- [x] Turkish interface with an EN/TR switch in the menu header
- [x] Build tools set up (arduino-cli, ESP32 core 3.3.3, libraries), see [building-firmware.md](../building-firmware.md)
- [x] Khan-Nomad firmware built: Khan-Nomad WiFi name, yurt on the LCD, Khan-Nomad on TVs

### Shopping

- [x] Waveshare ESP32-S3-LCD-1.47 (USB-A)
- [ ] microSD card: 128 GB (256 GB for Wikipedia with images), A1/U3

### Before the board arrives

- [ ] Print the case: `NomadCasev30.stl` (the USB-A one, not `_USB-C`)
- [ ] Convert movies to MP4 with the preset in `tools/handbrake`
- [ ] Collect music (MP3), books (ePub/PDF), comics (CBZ)
- [ ] Download a Wikipedia ZIM from Kiwix (`mini` 13 GB, `nopic` 49 GB, `maxi` 119 GB)
- [ ] Download [Nomad Tools](https://github.com/Jstudner/Nomad-Tools) for adding ZIMs

### When it arrives

- [ ] Flash the **Khan-Nomad firmware**: `JcorpNomadProject.ino.merged.bin` at `0x0` (see [building-firmware.md](../building-firmware.md)). The original firmware on nomadflash.jcorptech.net is the fallback.
- [ ] Copy this fork's `SD_Card_Template` onto the card, then copy media into the folders
- [ ] Add the Wikipedia ZIM with Nomad Tools
- [ ] Boot: the screen shows the yurt and a `Khan-Nomad` WiFi network appears (default password `password`)
- [ ] Open the menu, check the Steppe Night theme and the EN/TR switch
- [ ] **Change the WiFi password** (8+ characters) and **set an admin password**
- [ ] Gear icon, Library Index, **Full Scan Now**
- [ ] Assemble into the printed case

## 2. Bluetooth music player

Full plan, parts list and wiring: [bluetooth-music-player.md](bluetooth-music-player.md)

### Shopping

- [ ] ESP32-WROOM-32 DevKit (must be the original ESP32, not S3/C3/C6)
- [ ] 3.7V 2000 mAh protected LiPo, JST-PH 2.0
- [ ] TP4056 USB-C charger module with protection
- [ ] MT3608 boost converter
- [ ] Slide switch
- [ ] 0.96" SSD1306 I2C OLED
- [ ] 5 tactile buttons
- [ ] 2x 100 kOhm, 100 nF, 470 uF (check Makerspace drawers first)

### Build

- [ ] Breadboard ESP32 + OLED + buttons on USB power
- [ ] Firmware: buttons and screen
- [ ] Firmware: join Nomad WiFi, fetch the song list
- [ ] Firmware: stream and decode one MP3
- [ ] Firmware: Bluetooth A2DP output and controls
- [ ] Power section: set MT3608 to 5.0V **before** connecting the ESP32
- [ ] Solder onto perfboard, design and print the case

## Spare hardware

- ESP32-S3 DevKitC-1 (WROOM-1-N16R8): free for experiments. Can't do Bluetooth
  audio (no Bluetooth Classic), but could run Nomad with an SD breakout, see
  [main-nomad-on-devkitc.md](main-nomad-on-devkitc.md).
