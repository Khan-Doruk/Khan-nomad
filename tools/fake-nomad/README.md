# Fake Nomad

Run the Nomad web interface on your computer, no ESP32 needed.

`fake_nomad.py` serves a folder laid out like a Nomad SD card and answers the
same HTTP API as the firmware (`/listfiles`, `/api/index`, `/media` with range
requests, admin status, uploads...). The real pages from `SD_Card_Template`
run unchanged in your browser.

Useful for:

- Seeing and customizing the interface (themes, pages) before the board arrives
- Checking how your own movies, music and books look before copying them to the card
- Testing the [Bluetooth music player](../../docs/ideas/bluetooth-music-player.md)
  firmware against a "Nomad" on your WiFi

## Run it

Needs Python 3.9+ (standard library only, nothing to install).

```bash
python tools/fake-nomad/fake_nomad.py
```

Then open <http://localhost:8080>. The first run creates `tools/fake-nomad/card/`
as a copy of `SD_Card_Template` (git-ignored), so anything you change from the
admin page never touches the template.

Options:

| Flag | What it does |
|---|---|
| `--card PATH` | Serve another folder, for example a prepared SD card (`--card E:\`) |
| `--port N` | Use another port (default 8080) |
| `--lan` | Listen on your whole network so phones and ESP32s on the same WiFi can connect. Windows may ask to allow Python through the firewall. |

Put your own files in the card folder (`Movies/`, `Music/`, `Books/`...) and
refresh the page, there's no scan step.

## What works

Checked against the sample card: menu, movies (with seeking), music, books,
games, the Wikipedia ZIM in Archive, and the admin panel. Saving, uploading,
renaming and deleting files from the pages writes to the card folder.

## What's faked

- Device-only features succeed but do nothing: restart, USB mode, LEDs,
  brightness, WiFi mode, rescans.
- Status values are made up: 1 connected user, 41.5 °C, a 128 GB card.
- Local multiplayer (`/api/mp/*`) and DLNA aren't implemented.
- Indexes are built on every request instead of cached, so a huge card is slower
  than on the device. Real Nomad performance (an ESP32 over WiFi) will be much
  slower than this anyway.
