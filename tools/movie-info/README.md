# movie-info

Writes a small `<movie>.info.json` file next to every movie on a Nomad SD card,
so the Movies page can show the year, runtime, genres and a short description,
and a `show.info.json` in every show folder for the Shows page.

You run it on a laptop with the card (or a copy of it) plugged in. The Nomad
itself never goes online: it just reads the JSON files off the card.

## Run it

Python 3.8 or newer. The offline part uses only the standard library;
`--posters` also needs Pillow (`pip install pillow`).

```
python tools/movie-info/movie_info.py <card folder> [--online] [--posters] [--lang en|tr] [--overwrite]
```

`<card folder>` is the folder that holds `Movies/` and `Shows/` (the SD card's
root, for example `E:\`).

| option | what it does |
| --- | --- |
| *(none)* | Offline. Title and year come from the file name, runtime from the video file itself. |
| `--online` | Also looks the title up on Wikipedia: a short description (about 300 characters), genres, and the year if the file name had none. |
| `--posters` | With `--online`: if a movie has no poster image yet, saves the Wikipedia lead image as `<movie>.jpg` (max 600 px wide). For shows without a cover it saves `<Show>/poster.jpg`. |
| `--lang tr` | Uses tr.wikipedia.org instead of en.wikipedia.org (description and genre names in Turkish). |
| `--overwrite` | Rebuilds sidecars that already exist. Without it, existing files are left alone, except that `--online` fills in a sidecar that has no description yet (fields already in the file are kept). |

`--online` and `--posters` need internet on the laptop. The tool waits about
half a second between Wikipedia requests and backs off when Wikipedia asks it
to slow down. If a lookup fails, an existing sidecar is never replaced, and a
new one is written with the offline info only; run with `--online` again later
to fill it in.

At the end it prints a table: what was created, updated, skipped or failed,
the year and runtime it found, and a note (which Wikipedia page it used, poster
size, or why something was skipped).

### Getting good matches

Put the year in the file name: `Nosferatu (1922).mp4`, `The.Kid.1921.720p.mp4`
and `Metropolis 1927.mkv` all work. Without a year, Wikipedia's first film by
that name wins (`The Phantom of the Opera.mp4` gets the 2004 film, not 1925).
Release tags like `720p`, `BluRay`, `x264`, `[YTS]` are dropped from the title.

A result is only used when the Wikipedia page describes a film (or a TV series,
for shows), names the same title, and has no other year in its title or short
description. Anything else is reported as "no Wikipedia match" and the sidecar
keeps just the offline info. If a match is wrong, edit the JSON by hand (or
delete it and rename the video with the year).

## Where the files go

```
Movies/
  Nosferatu (1922).mp4
  Nosferatu (1922).jpg          <- poster (same base name; --posters adds it if missing)
  Nosferatu (1922).info.json    <- sidecar
  Classics/
    Metropolis.1927.mkv
    Metropolis.1927.info.json
Shows/
  Breaking Bad/
    show.info.json
    poster.jpg                   <- only if the show had no cover
    Season 1/...
```

Movies are read from `Movies/` and its direct sub-folders, the same depth the
Movies page reads.

## Sidecar format

Every field is optional; the pages show whatever is there.

```json
{
  "title": "Nosferatu",
  "year": 1922,
  "runtime": 94,
  "genres": ["Horror", "Silent"],
  "description": "Nosferatu: A Symphony of Horror is a 1922 silent German Expressionist vampire film directed by F. W. Murnau...",
  "source": "Wikipedia",
  "source_url": "https://en.wikipedia.org/wiki/Nosferatu"
}
```

| field | type | notes |
| --- | --- | --- |
| `title` | string | Replaces the cleaned-up file name in the movie sheet. |
| `year` | number | |
| `runtime` | number | Minutes. Read from MP4/M4V/MOV (`moov/mvhd`) and MKV/WebM (`Segment/Info/Duration`) headers, no ffmpeg needed. Left out for AVI and files it cannot read. |
| `genres` | array of strings | Picked out of Wikipedia's short description. |
| `description` | string | A few sentences. Shown clamped to 3 lines with a "More" toggle. |
| `source` | string | Shown in small print under the description (Wikipedia text is CC BY-SA, so keep the credit). |
| `source_url` | string | Not shown (the Nomad is offline), kept for reference. |

`show.info.json` uses the same fields; the Shows page shows `year` and
`description`.

You can write or edit these files by hand. Keep them UTF-8.
