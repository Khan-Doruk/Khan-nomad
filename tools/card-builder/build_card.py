#!/usr/bin/env python3
"""Khan-Nomad card builder: get an SD card ready in one command.

    python tools/card-builder/build_card.py E:\\                       # interface + folders + checks
    python tools/card-builder/build_card.py E:\\ --add D:\\Downloads\\Movies --add D:\\Music
    python tools/card-builder/build_card.py E:\\ --add ... --dry-run   # show the plan, change nothing

What it does:
  1. Checks the card: file system (exFAT / FAT32), free space, files over 4 GB on FAT32.
  2. Installs this fork's interface (pages, scripts, themes, built-in games, logo) and
     creates every media folder. With gzip on (the default) text files are stored as
     .gz, about 4x smaller, so the ESP32 reads and sends far less. That needs the
     Khan-Nomad firmware; use --no-gzip if the board runs the original firmware.
  3. Sorts anything passed with --add into the right folders: videos to Movies (or Shows
     for S01E02-style names), audio to Music, ebooks and comics to Books, pictures to
     Gallery, ZIMs to Archive, ROMs to Games, everything else to Files. Posters and
     subtitles next to a video travel with it; music keeps its album folders.
  4. Flags videos browsers can't play (MKV, AVI, ...) and, with --convert and ffmpeg
     installed, converts them to MP4 (H.264 + AAC).
  5. Prints a report: what was copied, what to fix, how full the card is.

Your media on the card is never deleted. Standard library only (Python 3.9+).
"""

import argparse
import gzip
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TEMPLATE = os.path.join(REPO, "SD_Card_Template")

MEDIA_FOLDERS = ["Movies", "Shows", "Music", "Books", "Gallery", "Files", "Games",
                 "Archive", "Maps", "Cookbook", "Workshop", "Translate"]
# template folders that are part of the interface, not sample media
INTERFACE_DIRS = ["assets", "EmulatorJS", "Games"]   # Games = the built-in games, their covers and the DOOM WAD
GZIP_EXTS = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".map"}
GZIP_SKIP_DIRS = {"EmulatorJS", "Games"}  # EmulatorJS fetches its own files; /api/games-list shows raw file names
SKIP_TEMPLATE_FILES = {"Nomad-Card-Tools.zip"}

VIDEO_OK = {".mp4", ".m4v", ".webm"}
VIDEO_CONVERT = {".mkv", ".avi", ".mov", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp"}
AUDIO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav", ".m4b"}
BOOKS = {".epub", ".pdf", ".txt", ".mobi", ".azw3", ".cbz", ".cbr", ".cb7"}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"}
SUBS = {".srt", ".vtt", ".ass", ".ssa", ".sub"}
ROMS = {".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".md", ".gen", ".z64", ".n64", ".sms", ".gg", ".wad"}
JUNK = {"thumbs.db", "desktop.ini", ".ds_store"}
SHOW_RX = re.compile(r"^(?P<show>.+?)[ ._-]+[Ss](?P<s>\d{1,2})[ ._-]?[Ee](?P<e>\d{1,3})")
FAT32_MAX = 4 * 1024 ** 3 - 1


# ---------------------------------------------------------------- helpers
def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def filesystem_of(path):
    """'exFAT', 'FAT32', 'NTFS'... or None if unknown (Windows only, via the volume API)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
        name = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(root, None, 0, None, None, None, name, 64)
        return name.value if ok else None
    except Exception:
        return None


class Report:
    def __init__(self):
        self.copied = []        # (dest, bytes)
        self.skipped = 0
        self.warnings = []
        self.todo = []

    def warn(self, msg):
        self.warnings.append(msg)

    def need(self, msg):
        self.todo.append(msg)


# ---------------------------------------------------------------- interface
def install_interface(card, use_gzip, dry, rep):
    """Copy pages, scripts and built-in games; gzip text files if asked."""
    written = 0

    def place(src, rel):
        nonlocal written
        ext = os.path.splitext(rel)[1].lower()
        top = rel.replace("\\", "/").split("/")[0]
        do_gz = use_gzip and ext in GZIP_EXTS and top not in GZIP_SKIP_DIRS
        dst = os.path.join(card, rel)
        plain, packed = dst, dst + ".gz"
        if dry:
            written += 1
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if do_gz:
            with open(src, "rb") as f:
                data = gzip.compress(f.read(), 9, mtime=0)
            with open(packed, "wb") as f:
                f.write(data)
            if os.path.exists(plain):       # the plain copy would win over the .gz
                os.remove(plain)
        else:
            shutil.copy2(src, plain)
            if os.path.exists(packed):      # stale .gz from an earlier gzip build
                os.remove(packed)
        written += 1

    for name in sorted(os.listdir(TEMPLATE)):
        src = os.path.join(TEMPLATE, name)
        if os.path.isfile(src) and name not in SKIP_TEMPLATE_FILES:
            place(src, name)
    for d in INTERFACE_DIRS:
        for root, _, files in os.walk(os.path.join(TEMPLATE, d)):
            for fn in files:
                src = os.path.join(root, fn)
                place(src, os.path.relpath(src, TEMPLATE))
    for d in MEDIA_FOLDERS:
        if not dry:
            os.makedirs(os.path.join(card, d), exist_ok=True)
    return written


# ---------------------------------------------------------------- media sorting
def classify(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_OK or ext in VIDEO_CONVERT:
        return "Shows" if SHOW_RX.match(os.path.basename(path)) else "Movies"
    if ext in AUDIO:
        return "Music"
    if ext in BOOKS:
        return "Books"
    if ext in IMAGES:
        return "Gallery"
    if ext == ".zim" or re.search(r"\.zim[a-z]{2}$", ext):
        return "Archive"
    if ext in ROMS:
        return "Games"
    return "Files"


def plan_media(sources):
    """Return [(src, dest_rel)] for every file under the --add sources."""
    plan = []
    for source in sources:
        source = os.path.abspath(source)
        if os.path.isfile(source):
            base = os.path.dirname(source)
            files = [source]
        else:
            base = os.path.dirname(source.rstrip("\\/"))
            files = [os.path.join(r, f) for r, _, fs in os.walk(source) for f in fs]
        # map video base names so posters and subtitles follow their video
        videos = {}
        for f in files:
            if classify(f) in ("Movies", "Shows"):
                videos[(os.path.dirname(f), os.path.splitext(os.path.basename(f))[0].lower())] = f
        for f in files:
            name = os.path.basename(f)
            if name.lower() in JUNK or name.startswith("._"):
                continue
            ext = os.path.splitext(name)[1].lower()
            stem = os.path.splitext(name)[0].lower()
            owner = None
            if ext in IMAGES or ext in SUBS or name.lower().endswith(".info.json"):
                key_stem = stem[:-5] if stem.endswith(".info") else stem
                for (d, vstem), v in videos.items():
                    if d == os.path.dirname(f) and (key_stem == vstem or key_stem.startswith(vstem + ".")):
                        owner = v
                        break
            bucket = classify(owner or f)
            if owner and bucket == "Gallery":
                bucket = classify(owner)
            if bucket == "Shows":
                m = SHOW_RX.match(os.path.basename(owner or f))
                show = re.sub(r"[._]+", " ", m.group("show")).strip().title()
                dest = os.path.join("Shows", show, f"Season {int(m.group('s'))}", name)
            elif bucket == "Music":
                # keep at most the artist/album folders the song sits in
                parts = os.path.relpath(f, source if os.path.isdir(source) else base).split(os.sep)
                dest = os.path.join("Music", *parts[-3:])
            else:
                dest = os.path.join(bucket, name)
            plan.append((f, dest))
    return plan


def find_ffmpeg():
    return shutil.which("ffmpeg")


def convert_video(ffmpeg, src, dst):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
           "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-vf", "scale='min(1280,iw)':-2", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", dst]
    return subprocess.run(cmd).returncode == 0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Get a Khan-Nomad SD card ready.")
    ap.add_argument("card", help="the SD card (drive root like E:\\) or any folder to build into")
    ap.add_argument("--add", action="append", default=[], metavar="PATH",
                    help="file or folder of media to sort onto the card (repeatable)")
    ap.add_argument("--no-gzip", action="store_true",
                    help="store interface files uncompressed (needed with the ORIGINAL firmware)")
    ap.add_argument("--convert", action="store_true",
                    help="convert MKV/AVI/MOV... to MP4 with ffmpeg (slow; needs ffmpeg on PATH)")
    ap.add_argument("--no-interface", action="store_true", help="only sort media, don't touch the interface")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    args = ap.parse_args()

    card = os.path.abspath(args.card)
    dry = args.dry_run
    rep = Report()
    if not os.path.isdir(card):
        sys.exit(f"Card folder not found: {card}")

    print(f"Khan-Nomad card builder{'  (dry run, nothing will change)' if dry else ''}")
    print(f"Card: {card}")

    # ---- 1. card checks
    fs = filesystem_of(card)
    usage = shutil.disk_usage(card)
    print(f"File system: {fs or 'unknown'}   free {human(usage.free)} of {human(usage.total)}")
    drive_root = os.path.splitdrive(card)[1] in ("\\", "/", "")
    if not drive_root:
        rep.warn("This is a folder, not the root of a drive. Nomad reads the card's root, so copy "
                 "this folder's contents to the card root afterwards (fine for testing).")
    if fs and fs.upper() not in ("EXFAT", "FAT32", "FAT"):
        rep.warn(f"{fs} cards don't work in Nomad. Format the card as exFAT.")
    fat32 = bool(fs and fs.upper() in ("FAT32", "FAT"))

    # ---- 2. interface
    if not args.no_interface:
        if not args.no_gzip:
            print("Interface: gzipped (needs the Khan-Nomad firmware; use --no-gzip for the original)")
        n = install_interface(card, not args.no_gzip, dry, rep)
        print(f"Interface: {n} files {'would be ' if dry else ''}installed, media folders ready")

    # ---- 3. media
    plan = plan_media(args.add) if args.add else []
    need = sum(os.path.getsize(s) for s, d in plan
               if not (os.path.exists(os.path.join(card, d)) and os.path.getsize(os.path.join(card, d)) == os.path.getsize(s)))
    if plan:
        print(f"Media: {len(plan)} files to sort, {human(need)} to copy")
        if need > usage.free:
            sys.exit(f"Not enough space: need {human(need)}, card has {human(usage.free)} free.")
    ffmpeg = find_ffmpeg() if args.convert else None
    if args.convert and not ffmpeg:
        rep.warn("--convert needs ffmpeg on PATH (winget install Gyan.FFmpeg). Skipping conversions.")

    for src, rel in plan:
        dst = os.path.join(card, rel)
        size = os.path.getsize(src)
        ext = os.path.splitext(src)[1].lower()
        if fat32 and size > FAT32_MAX:
            rep.warn(f"{os.path.basename(src)} is {human(size)}, over FAT32's 4 GB limit. Use an exFAT card.")
            continue
        if ext in VIDEO_CONVERT and rel.startswith(("Movies", "Shows")):
            mp4 = os.path.splitext(dst)[0] + ".mp4"
            if ffmpeg:
                if os.path.exists(mp4):
                    rep.skipped += 1
                    continue
                print(f"  converting {os.path.basename(src)} -> MP4 ...")
                if not dry:
                    os.makedirs(os.path.dirname(mp4), exist_ok=True)
                    if convert_video(ffmpeg, src, mp4):
                        rep.copied.append((mp4, os.path.getsize(mp4)))
                    else:
                        rep.warn(f"ffmpeg could not convert {src}")
                continue
            rep.need(f"{os.path.basename(src)}: browsers can't play {ext.upper()[1:]}, so it wasn't copied. "
                     f"Convert it to MP4 (HandBrake preset in tools/handbrake, or rerun with --convert).")
            continue
        if os.path.exists(dst) and os.path.getsize(dst) == size:
            rep.skipped += 1
            continue
        if not dry:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        rep.copied.append((dst, size))
        if rel.startswith("Archive"):
            rep.need(f"{os.path.basename(src)}: run Nomad Tools \"Add ZIM archives\" so Nomad can search it.")
        if len(rep.copied) % 25 == 0:
            print(f"  ... {len(rep.copied)} files copied")

    # ---- 4. report
    print("\n=== Report ===")
    if plan:
        by = {}
        for dst, size in rep.copied:
            b = os.path.relpath(dst, card).split(os.sep)[0]
            by[b] = by.get(b, 0) + size
        print(f"Copied {len(rep.copied)} files ({human(sum(by.values()))}), skipped {rep.skipped} already on the card")
        for b, size in sorted(by.items()):
            print(f"  {b:<10} {human(size)}")
    for d in MEDIA_FOLDERS:
        p = os.path.join(card, d)
        if os.path.isdir(p):
            files = sum(len(fs_) for _, _, fs_ in os.walk(p))
            if files:
                print(f"  /{d}: {files} files")
    for w in rep.warnings:
        print("WARNING:", w)
    for t in sorted(set(rep.todo)):
        print("TO DO:", t)
    if not dry:
        u = shutil.disk_usage(card)
        print(f"Card: {human(u.used)} used, {human(u.free)} free")
    print("\nNext: put the card in the Nomad, open the menu, gear icon > Library Index > Full Scan Now.")
    if not any(a.startswith("--movie") for a in sys.argv):
        print("Tip: python tools/movie-info/movie_info.py <card> --online --posters adds movie details.")


if __name__ == "__main__":
    main()
