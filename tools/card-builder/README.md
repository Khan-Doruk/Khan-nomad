# Card builder

Gets a Khan-Nomad SD card ready in one command: installs the interface,
creates every folder, sorts your media into the right places and checks the
card for problems.

```bash
python tools/card-builder/build_card.py E:\
python tools/card-builder/build_card.py E:\ --add D:\Downloads\Movies --add D:\Music --add D:\Books
```

Replace `E:\` with your SD card's drive. Python 3.9+, no extra packages.

## What it does

1. **Checks the card**: file system (exFAT is best, FAT32 works, NTFS doesn't),
   free space, and files over FAT32's 4 GB limit.
2. **Installs the interface** from this fork's `SD_Card_Template`: pages,
   scripts, themes, logo, built-in games, the emulator. It doesn't copy the
   sample movies/music/books. Running it again updates the interface and never
   touches your media.
3. **Sorts media** given with `--add` (files or folders, as many as you like):

   | Goes to | What |
   |---|---|
   | Movies | MP4 / M4V / WebM videos, plus a poster image and `.srt`/`.vtt` subtitles with the same name |
   | Shows/&lt;Show&gt;/Season N | videos named like `Show.Name.S01E02...` |
   | Music/&lt;Artist&gt;/&lt;Album&gt; | MP3, M4A, FLAC, OGG, WAV... (keeps up to artist/album folders) |
   | Books | EPUB, PDF, TXT, CBZ/CBR comics |
   | Gallery | pictures that aren't a video's poster |
   | Archive | `.zim` files (then run Nomad Tools "Add ZIM archives") |
   | Games | ROMs and `.wad` files |
   | Files | everything else |

   Files already on the card with the same size are skipped, so you can rerun it
   after adding more. `Thumbs.db`, `desktop.ini` and macOS `._` files are left out.
4. **Videos browsers can't play** (MKV, AVI, MOV, WMV...) aren't copied, and
   the report lists them. Convert them with the HandBrake preset in
   `tools/handbrake`, or install ffmpeg (`winget install Gyan.FFmpeg`) and add
   `--convert` to turn them into MP4 (H.264 + AAC, max 1280 px wide) automatically.
5. **Report**: what was copied per folder, what still needs doing, how full the card is.

## Faster pages (gzip)

By default the interface files (HTML, JavaScript, CSS, JSON) are stored
**gzip-compressed** as `page.html.gz`. That makes them about 4x smaller (all the
main pages together: 4.7 MB down to 1.2 MB), so the ESP32 reads far less from
the SD card and sends far less over WiFi. Browsers unpack them automatically.

This needs the **Khan-Nomad firmware**, which knows to serve `x.gz` when `x`
isn't there. If the board runs the original Jcorp Nomad firmware, add
`--no-gzip`, otherwise the pages won't load.

## Options

| Option | |
|---|---|
| `--add PATH` | media to sort onto the card (repeatable) |
| `--dry-run` | show what would happen, change nothing |
| `--convert` | convert unplayable videos to MP4 with ffmpeg |
| `--no-gzip` | store the interface uncompressed (original firmware) |
| `--no-interface` | only sort media |

## After building

1. Optional: `python tools/movie-info/movie_info.py E:\ --online --posters`
   adds years, runtimes, descriptions and missing posters.
2. Put the card in the Nomad, open the menu, gear icon, Library Index,
   **Full Scan Now**.

To try a built card on your laptop first:
`python tools/fake-nomad/fake_nomad.py --card E:\` (the fake Nomad serves the
`.gz` files the same way the firmware does).
