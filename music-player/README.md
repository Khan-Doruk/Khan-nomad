# Khan-Nomad music player firmware

Firmware for the Bluetooth music player companion
([plan, parts and wiring](../docs/ideas/bluetooth-music-player.md)).
It's built in steps so each part can be tested before the hardware is
finished.

| Step | What it adds | Board | Status |
|---|---|---|---|
| **1** | Join the Nomad WiFi, read the song list, stream and decode MP3s, buttons and serial commands | ESP32-S3 DevKitC-1 or ESP32-WROOM-32 | **Done (compiles, not yet run on hardware)** |
| 2 | OLED: song title, progress, volume, battery | either | Planned |
| 3 | Battery sense on GPIO34 | WROOM-32 | Planned |
| 4 | Bluetooth A2DP to a speaker or headphones | **WROOM-32 only** (the S3 has no Bluetooth Classic) | Planned |

## Step 1: what it does

`firmware/NomadPlayer/NomadPlayer.ino`:

1. Joins the WiFi network saved in flash (default `Khan-Nomad` / `password`).
2. Reads the song list from Nomad's index: `GET /api/index?path=/Music`
   (NDJSON), keeping MP3 files (up to 500).
3. Streams a song from `GET /media?file=<path>` through a 16 KB buffer and
   decodes it with the Helix MP3 decoder (ESP8266Audio).
4. Sends the decoded audio to a **meter** instead of a speaker: it plays at
   real speed and prints progress and level every 3 seconds. If the meter
   keeps time, the streaming works; step 4 swaps the meter for Bluetooth.
5. Five buttons (to GND, internal pull-ups): play/pause, previous, next,
   volume down, volume up.

| Button | WROOM-32 pin | S3 DevKitC-1 pin |
|---|---|---|
| Play / pause | GPIO32 | GPIO4 |
| Previous | GPIO33 | GPIO5 |
| Next | GPIO25 | GPIO6 |
| Volume down | GPIO26 | GPIO7 |
| Volume up | GPIO27 | GPIO15 |

Serial commands (115200 baud): `list`, `play <n>`, `p` (pause), `n` / `b`
(next / previous), `+` / `-`, `status`, `scan`, `wifi <ssid> <password>`,
`host <ip[:port]>`, `help`. WiFi and host settings are saved in flash.

## Test it before the Nomad arrives

Use the fake Nomad on your laptop as the server, over your normal WiFi:

1. On the laptop, start the fake Nomad so other devices can reach it:
   ```bash
   python tools/fake-nomad/fake_nomad.py --lan
   ```
   It prints an address like `http://192.168.1.23:8080`. Allow Python through
   the Windows firewall if asked. Put a few MP3s in
   `tools/fake-nomad/card/Music/`.
2. Flash the ESP32 (see below) and open the serial monitor:
   ```bash
   arduino-cli monitor -p COM5 -c baudrate=115200
   ```
3. Point it at your WiFi and the laptop:
   ```
   wifi MyHomeWifi mypassword
   host 192.168.1.23:8080
   list
   play 1
   ```
   You should see `[meter] 0:03 |#######             | peak 15234` lines
   ticking once a second of music per second. Try `p`, `n`, `+`.

The demo songs in the sample card are tiny, so add a real MP3 or two to see
a full song stream.

When the real Nomad arrives: `wifi Khan-Nomad <your password>` and
`host 192.168.4.1`.

## Build and flash

Needs the setup from [docs/building-firmware.md](../docs/building-firmware.md)
plus one library:

```bash
arduino-cli lib install "ESP8266Audio@2.4.1"
```

ESP32-S3 DevKitC-1 (the board you have now):

```bash
arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi" --output-dir build/player-s3 music-player/firmware/NomadPlayer
arduino-cli upload -p COM5 --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi" --input-dir build/player-s3 music-player/firmware/NomadPlayer
```

ESP32-WROOM-32 (the final player board; "Huge APP" leaves room for Bluetooth):

```bash
arduino-cli compile --fqbn "esp32:esp32:esp32:PartitionScheme=huge_app" --output-dir build/player-wroom music-player/firmware/NomadPlayer
```

The first build takes a while because ESP8266Audio compiles all of its
codecs.
