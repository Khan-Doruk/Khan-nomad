#!/usr/bin/env python3
"""Khan-Nomad movie info: write <movie>.info.json sidecars (and optional posters)
next to the videos on a Nomad SD card, so movies.html / shows.html can show the
year, runtime, genres and a short description without any internet on the Nomad.

    python movie_info.py <card folder> [--online] [--posters] [--lang en|tr] [--overwrite]

Offline it reads the runtime from the file headers (MP4/M4V/MOV and MKV/WebM,
no ffmpeg needed) and the title/year from the filename. --online adds a
Wikipedia summary, --posters downloads a small poster where none exists.
Standard library only, except --posters which needs Pillow (PIL).
"""

import argparse
import html
import io
import json
import os
import re
import struct
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}   # same list as movies.html
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
INFO_SUFFIX = ".info.json"
SHOW_INFO = "show.info.json"
# Wikimedia asks for a descriptive User-Agent with a way to find the project
USER_AGENT = "Khan-Nomad movie-info (personal offline media server; https://github.com/Khan-Doruk/Khan-nomad)"
REQUEST_GAP = 0.5            # seconds between Wikipedia requests
DESC_MAX = 300               # description length target, cut at a sentence boundary
POSTER_MAX_W = 600           # posters are read off an SD card by an ESP32, keep them small
MAX_IMAGE_BYTES = 20 * 1024 * 1024


# --------------------------------------------------------------------------
# Runtime: MP4 / MOV (ISO BMFF boxes)
# --------------------------------------------------------------------------

def _box_header(f, end):
    """Read one box header at the current position. Returns (type, payload_start, box_end)
    or None. Handles 64-bit sizes (size == 1) and 'rest of the container' (size == 0)."""
    start = f.tell()
    if end - start < 8:
        return None
    hdr = f.read(8)
    if len(hdr) < 8:
        return None
    size, btype = struct.unpack(">I4s", hdr)
    payload = start + 8
    if size == 1:
        ext = f.read(8)
        if len(ext) < 8:
            return None
        size = struct.unpack(">Q", ext)[0]
        payload += 8
    elif size == 0:
        size = end - start
    if size < payload - start:
        return None
    return btype, payload, min(start + size, end)


def _iter_boxes(f, start, end):
    pos = start
    while pos < end:
        f.seek(pos)
        h = _box_header(f, end)
        if not h:
            return
        yield h
        if h[2] <= pos:
            return
        pos = h[2]


def mp4_duration(path):
    """Seconds from moov/mvhd (or moov/mvex/mehd for fragmented files), or None.
    Only box headers and the small mvhd/mehd payloads are read; moov may sit at the end."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_end = f.tell()
        for btype, payload, bend in _iter_boxes(f, 0, file_end):
            if btype != b"moov":
                continue
            timescale, duration = None, None
            frag = None
            for ctype, cpay, cend in _iter_boxes(f, payload, bend):
                if ctype == b"mvhd":
                    f.seek(cpay)
                    data = f.read(min(32, cend - cpay))
                    if len(data) < 20:
                        continue
                    version = data[0]
                    if version == 1:
                        if len(data) < 32:
                            continue
                        timescale, duration = struct.unpack(">IQ", data[20:32])
                        unknown = 0xFFFFFFFFFFFFFFFF
                    else:
                        timescale, duration = struct.unpack(">II", data[12:20])
                        unknown = 0xFFFFFFFF
                    if duration == unknown:
                        duration = None
                elif ctype == b"mvex":
                    for gtype, gpay, gend in _iter_boxes(f, cpay, cend):
                        if gtype == b"mehd":
                            f.seek(gpay)
                            data = f.read(min(12, gend - gpay))
                            if len(data) >= 12 and data[0] == 1:
                                frag = struct.unpack(">Q", data[4:12])[0]
                            elif len(data) >= 8:
                                frag = struct.unpack(">I", data[4:8])[0]
            if not duration and frag:
                duration = frag
            if timescale and duration:
                return duration / float(timescale)
            return None
    return None


# --------------------------------------------------------------------------
# Runtime: Matroska / WebM (EBML Segment > Info > Duration)
# --------------------------------------------------------------------------

EBML_HEADER = 0x1A45DFA3
SEGMENT = 0x18538067
INFO = 0x1549A966
TIMECODE_SCALE = 0x2AD7B1
DURATION = 0x4489
CLUSTER = 0x1F43B675


def _ebml_id(f):
    b = f.read(1)
    if not b:
        return None
    first = b[0]
    length = 1
    mask = 0x80
    while length <= 4 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 4:
        return None
    rest = f.read(length - 1)
    if len(rest) < length - 1:
        return None
    return int.from_bytes(b + rest, "big")


def _ebml_size(f):
    """Returns (size, unknown_flag) or (None, False) at EOF."""
    b = f.read(1)
    if not b:
        return None, False
    first = b[0]
    length = 1
    mask = 0x80
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8:
        return None, False
    rest = f.read(length - 1)
    if len(rest) < length - 1:
        return None, False
    value = first & (mask - 1)
    for c in rest:
        value = (value << 8) | c
    unknown = value == (1 << (7 * length)) - 1
    return value, unknown


def mkv_duration(path):
    """Seconds from Segment/Info/Duration, or None. Only element headers are read."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_end = f.tell()
        f.seek(0)
        if _ebml_id(f) != EBML_HEADER:
            return None
        size, unknown = _ebml_size(f)
        if size is None or unknown:
            return None
        f.seek(f.tell() + size)
        # top level: find the Segment
        for _ in range(16):
            eid = _ebml_id(f)
            size, unknown = _ebml_size(f)
            if eid is None or size is None:
                return None
            if eid == SEGMENT:
                seg_end = file_end if unknown else min(file_end, f.tell() + size)
                break
            if unknown:
                return None
            f.seek(f.tell() + size)
        else:
            return None
        # segment children: Info normally comes right after SeekHead / Void
        for _ in range(64):
            if f.tell() >= seg_end:
                return None
            eid = _ebml_id(f)
            size, unknown = _ebml_size(f)
            if eid is None or size is None:
                return None
            if eid == CLUSTER:
                return None              # media data started, Info was not up front
            if unknown:
                return None
            if eid == INFO:
                info_end = f.tell() + size
                scale, dur = 1000000, None
                while f.tell() < info_end:
                    cid = _ebml_id(f)
                    csize, cunk = _ebml_size(f)
                    if cid is None or csize is None or cunk:
                        break
                    data_pos = f.tell()
                    if cid == TIMECODE_SCALE and 0 < csize <= 8:
                        scale = int.from_bytes(f.read(csize), "big") or 1000000
                    elif cid == DURATION and csize in (4, 8):
                        raw = f.read(csize)
                        dur = struct.unpack(">f" if csize == 4 else ">d", raw)[0]
                    f.seek(data_pos + csize)
                if dur and dur > 0:
                    return dur * scale / 1e9
                return None
            f.seek(f.tell() + size)
    return None


def video_runtime_minutes(path):
    """Runtime in whole minutes, or None when it cannot be read."""
    e = os.path.splitext(path)[1].lower()
    try:
        if e in (".mp4", ".m4v", ".mov"):
            sec = mp4_duration(path)
        elif e in (".mkv", ".webm"):
            sec = mkv_duration(path)
        else:
            sec = None
    except (OSError, struct.error, ValueError, OverflowError):
        sec = None
    if not sec or sec <= 0 or sec > 100 * 3600:
        return None
    return max(1, int(round(sec / 60.0)))


# --------------------------------------------------------------------------
# Title / year from a filename
# --------------------------------------------------------------------------

JUNK = re.compile(
    r"^(?:\d{3,4}p|4k|uhd|hd|fhd|sd|hdr\d*|dv|10bit|8bit|bluray|blu-ray|bdrip|brrip|bdremux|remux|"
    r"webrip|web-?dl|web|hdtv|hdrip|dvdrip|dvdscr|dvd|xvid|divx|x26[45]|h\.?26[45]|hevc|avc|"
    r"aac\d*(?:\.\d)?|ac3|dts|ddp?\d*(?:\.\d)?|atmos|truehd|mp3|flac|5\.1|7\.1|yify|yts|rarbg|"
    r"proper|repack|extended|unrated|remastered|internal|limited|multi|dubbed|subbed|"
    r"subs?|engsub|tr|eng|en|türkçe|turkce|dublaj|altyazi|altyazılı)$",
    re.IGNORECASE)
YEAR = re.compile(r"(?<!\d)(18[89]\d|19\d\d|20\d\d)(?!\d)")


def clean_title(name):
    """'The.Kid.1921.720p.mp4' -> ('The Kid', 1921). The year is kept in the title when it
    is the whole name ('1917.mp4') or sits at the very start ('2001 A Space Odyssey')."""
    base = os.path.splitext(name)[0] if os.path.splitext(name)[1].lower() in VIDEO_EXTS else name
    s = base
    if " " not in s.strip():
        s = re.sub(r"[._]+", " ", s)
    else:
        s = s.replace("_", " ")
    # bracket groups: (1922) is the year, [..] and tag-only (..) are release junk,
    # other (..) stay part of the title. A marker token ends the title there.
    year = None

    def bracket(m):
        nonlocal year
        inner = m.group(2).strip()
        y = YEAR.fullmatch(inner)
        if y:
            year = year or int(y.group(1))
            return " \x00 "
        if m.group(1) == "[" or not inner or any(JUNK.match(t) for t in inner.split()):
            return " \x01 "
        return " (" + inner + ") "

    s = re.sub(r"([\[(])([^\])]*)[\])]", bracket, s)
    tokens = s.split()
    out = []
    for i, tok in enumerate(tokens):
        if tok in ("\x00", "\x01"):
            if out:
                break
            continue
        y = YEAR.fullmatch(tok.strip("-.,"))
        if y and out:                      # a year after some title words ends the title
            year = year or int(y.group(1))
            break
        if JUNK.match(tok.strip("-.,")) and out:
            break
        out.append(tok)
    title = " ".join(out).strip(" -_.,")
    if not title:
        title = base.strip()
    if title.islower():
        title = " ".join(w[:1].upper() + w[1:] for w in title.split())
    return title, year


# --------------------------------------------------------------------------
# Wikipedia
# --------------------------------------------------------------------------

# what a matching search hit's short description must (and must not) contain
FILM_WORDS = {"en": r"\b(?:film|movie)\b", "tr": r"\bfilm"}
SHOW_WORDS = {"en": r"\b(?:television series|tv series|web series|sitcom|miniseries|anime|"
                    r"animated series|television program(?:me)?|drama series)\b",
              "tr": r"\b(?:dizi|televizyon|anime)"}
FILM_NOT = {"en": r"\b(?:director|actor|actress|producer|screenwriter|filmmaker|cinematographer|critic|"
                  r"composer|editor|studio|company|festival|awards?|character|franchise|soundtrack|"
                  r"film series|list of|topics referred to)\b",
            "tr": r"(?:yönetmen|oyuncu|yapımcı|senarist|şirket|festival|ödül|karakter|serisi|anlam ayrımı)"}
SHOW_NOT = {"en": r"\b(?:episode|season \d|character|actor|actress|producer|list of|topics referred to)\b",
            "tr": r"(?:bölüm|karakter|oyuncu|anlam ayrımı)"}
SEARCH_TAG = {("movie", "en"): "film", ("movie", "tr"): "film",
              ("show", "en"): "TV series", ("show", "tr"): "dizi"}
GENRES = {
    "en": [("science fiction", "Science Fiction"), ("sci-fi", "Science Fiction"),
           ("horror", "Horror"), ("comedy", "Comedy"), ("comedic", "Comedy"), ("drama", "Drama"),
           ("thriller", "Thriller"), ("western", "Western"), ("documentary", "Documentary"),
           ("animated", "Animation"), ("animation", "Animation"), ("fantasy", "Fantasy"),
           ("romantic", "Romance"), ("romance", "Romance"), ("musical", "Musical"),
           ("war", "War"), ("crime", "Crime"), ("action", "Action"), ("adventure", "Adventure"),
           ("mystery", "Mystery"), ("biographical", "Biography"), ("superhero", "Superhero"),
           ("family", "Family"), ("noir", "Film Noir"), ("sports", "Sports"), ("silent", "Silent")],
    "tr": [("bilim kurgu", "Bilim kurgu"), ("bilimkurgu", "Bilim kurgu"), ("korku", "Korku"),
           ("komedi", "Komedi"), ("dram", "Dram"), ("gerilim", "Gerilim"), ("western", "Western"),
           ("kovboy", "Western"), ("belgesel", "Belgesel"), ("animasyon", "Animasyon"),
           ("fantastik", "Fantastik"), ("romantik", "Romantik"), ("müzikal", "Müzikal"),
           ("savaş", "Savaş"), ("suç", "Suç"), ("aksiyon", "Aksiyon"), ("macera", "Macera"),
           ("gizem", "Gizem"), ("biyografi", "Biyografi"), ("aile", "Aile"), ("sessiz", "Sessiz")],
}
MAX_GENRES = 4


class Wiki:
    def __init__(self, lang):
        self.lang = lang
        self.last = 0.0
        self.requests = 0

    def _get(self, url, binary=False, limit=2 * 1024 * 1024):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "*/*" if binary else "application/json"})
        for attempt in range(4):
            wait = REQUEST_GAP - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.requests += 1
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read(limit + 1)
                break
            except urllib.error.HTTPError as e:
                # rate limited or briefly unavailable: wait as told (or back off) and retry
                if e.code not in (429, 503) or attempt == 3:
                    raise
                try:
                    delay = float(e.headers.get("Retry-After") or 0)
                except (TypeError, ValueError):
                    delay = 0
                delay = min(60.0, max(delay, 5.0 * (attempt + 1)))
                print("    Wikipedia says %d, waiting %ds" % (e.code, delay), flush=True)
                time.sleep(delay)
        if len(data) > limit:
            raise ValueError("response too large")
        return data if binary else json.loads(data.decode("utf-8"))

    def search(self, query, limit=10):
        url = "https://%s.wikipedia.org/w/rest.php/v1/search/page?%s" % (
            self.lang, urllib.parse.urlencode({"q": query, "limit": limit}))
        return self._get(url).get("pages") or []

    def summary(self, key):
        url = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (
            self.lang, urllib.parse.quote(key.replace(" ", "_"), safe=""))
        return self._get(url)

    def image(self, url):
        return self._get(url, binary=True, limit=MAX_IMAGE_BYTES)


def _norm(s):
    s = unicodedata.normalize("NFKD", re.sub(r"\(.*?\)", " ", s or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("ı", "i")
    s = re.sub(r"[^\w]+", " ", s)
    return " ".join(w for w in s.split() if w not in ("the", "a", "an"))


def title_fits(want, page):
    """Does the page (title or the redirect it was found by) name the movie we have?
    Keeps a search for 'MoviePlaceholder film' from landing on some random film."""
    names = [page.get("title"), page.get("matched_title")]
    w = set(want.split())
    if not w:
        return False
    for n in names:
        got = _norm(n)
        if not got:
            continue
        if got == want or want in got or got in want:
            return True
        g = set(got.split())
        if len(w & g) / float(len(w)) >= 0.6 and len(w & g) / float(len(g)) >= 0.5:
            return True
    return False


def _years(text):
    return [int(y) for y in YEAR.findall(text or "")]


def pick_page(pages, title, year, yes, no):
    """Best search hit. It has to look like a film/series (yes) and not like a person,
    company or list (no), and name our title. A matching year pushes it up, another
    year in its title/description (a remake, a sequel) rules it out.
    Hits without a description (common on tr.wikipedia) are judged by their excerpt."""
    best, best_score = None, 0
    want = _norm(title)
    for i, p in enumerate(pages):
        desc = p.get("description") or ""
        head = (desc + " " + (p.get("title") or "")).lower()
        excerpt = ""
        if not desc:
            excerpt = html.unescape(re.sub(r"<[^>]+>", "", p.get("excerpt") or "")).lower()
        if not re.search(yes, head + " " + excerpt) or re.search(no, desc.lower()):
            continue
        if not title_fits(want, p):
            continue
        score = 5 - min(i, 4)                      # earlier hits are usually better
        if year:
            near = lambda ys: any(abs(y - year) <= 1 for y in ys)
            hy, ey = _years(head), _years(excerpt)
            if hy and not near(hy):
                continue                            # e.g. "1979 film" when we want 1922
            if near(hy):
                score += 6
            elif near(ey):
                score += 3
            elif ey:
                score -= 4
        if _norm(p.get("title")) == want:
            score += 4
        elif want and want in _norm(p.get("title")):
            score += 1
        if score > best_score:
            best, best_score = p, score
    return best


def trim_description(text, limit=DESC_MAX):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9\"'(])", text)
    out = ""
    for s in sentences:
        if out and len(out) + 1 + len(s) > limit:
            break
        out = (out + " " + s).strip() if out else s
    if len(out) > limit + 60:                       # one very long first sentence
        cut = out[:limit].rsplit(" ", 1)[0].rstrip(",;:-")
        out = cut + "…"
    return out


def genres_from(text, lang):
    t = " " + (text or "").lower() + " "
    found = []
    # Turkish words take suffixes ("korku filmi", "dramı"), so only the start is anchored there
    tail = "" if lang == "tr" else r"(?![\w])"
    for word, label in GENRES.get(lang, []):
        if re.search(r"(?<![\w-])" + re.escape(word) + tail, t) and label not in found:
            found.append(label)
    return found[:MAX_GENRES]


def lookup(wiki, title, year, kind):
    """Returns (info dict, image url or None, note). info may be empty when nothing fits."""
    yes = (FILM_WORDS if kind == "movie" else SHOW_WORDS)[wiki.lang]
    no = (FILM_NOT if kind == "movie" else SHOW_NOT)[wiki.lang]
    tag = SEARCH_TAG[(kind, wiki.lang)]
    queries = []
    if year:
        queries.append("%s %s %s" % (title, year, tag))
    queries.append("%s %s" % (title, tag))
    page = None
    for q in queries:
        page = pick_page(wiki.search(q), title, year, yes, no)
        if page:
            break
    if not page:
        return {}, None, "no Wikipedia match"
    s = wiki.summary(page.get("key") or page.get("title"))
    if s.get("type") == "disambiguation":
        return {}, None, "Wikipedia page is a disambiguation"
    info = {}
    desc_line = s.get("description") or page.get("description") or ""
    extract = s.get("extract") or ""
    first_sentence = re.split(r"(?<=[.!?])\s", extract, maxsplit=1)[0]
    if not year:
        m = YEAR.search(desc_line) or YEAR.search(first_sentence)
        if m:
            info["year"] = int(m.group(1))
    g = genres_from(desc_line + " " + first_sentence, wiki.lang)
    if g:
        info["genres"] = g
    if extract:
        info["description"] = trim_description(extract)
    info["source"] = "Wikipedia"
    url = ((s.get("content_urls") or {}).get("desktop") or {}).get("page")
    if url:
        info["source_url"] = url
    img = (s.get("originalimage") or {}).get("source") or (s.get("thumbnail") or {}).get("source")
    return info, img, "Wikipedia: " + (s.get("title") or page.get("title") or "")


def save_poster(wiki, url, dest):
    """Download, shrink to POSTER_MAX_W wide and save as JPEG. Returns a note."""
    try:
        from PIL import Image
    except ImportError:
        return "Pillow not installed, no poster"
    if url.lower().endswith(".svg"):
        return "Wikipedia image is an SVG, no poster"
    data = wiki.image(url)
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    elif im.mode == "L":
        im = im.convert("RGB")
    if im.width > POSTER_MAX_W:
        h = max(1, round(im.height * POSTER_MAX_W / im.width))
        im = im.resize((POSTER_MAX_W, h), Image.LANCZOS)
    tmp = dest + ".part"
    im.save(tmp, "JPEG", quality=82, optimize=True, progressive=True)
    os.replace(tmp, dest)
    return "poster %dx%d, %d KB" % (im.width, im.height, os.path.getsize(dest) // 1024)


# --------------------------------------------------------------------------
# Card walking
# --------------------------------------------------------------------------

def visible(name):
    return not name.startswith(".") and not name.startswith("._")


def find_movies(movies_dir):
    """Videos in /Movies and its direct sub-folders (the depth movies.html reads)."""
    out = []
    for root, dirs, files in os.walk(movies_dir):
        depth = os.path.relpath(root, movies_dir).count(os.sep) + (0 if root == movies_dir else 1)
        dirs[:] = sorted(d for d in dirs if visible(d)) if depth < 1 else []
        for f in sorted(files, key=str.lower):
            if visible(f) and os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                out.append(os.path.join(root, f))
    return out


def has_poster(folder, base):
    """Same rule as movies.html: an image whose name minus extension matches (any case)."""
    b = base.lower()
    try:
        for f in os.listdir(folder):
            stem, e = os.path.splitext(f)
            if e.lower() in IMAGE_EXTS and stem.lower() == b:
                return True
    except OSError:
        pass
    return False


def show_has_cover(shows_dir, show_dir):
    """Same rules as shows.html: poster/cover/folder/art image inside, or <Show>.jpg next to it."""
    try:
        for f in os.listdir(show_dir):
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS and \
                    any(k in f.lower() for k in ("poster", "cover", "folder", "art")):
                return True
    except OSError:
        pass
    name = os.path.basename(show_dir).lower()
    cands = {name, name.replace(" ", "-"), name.replace(" ", "_")}
    for f in os.listdir(shows_dir):
        stem, e = os.path.splitext(f)
        if e.lower() in IMAGE_EXTS and stem.lower() in cands:
            return True
    return False


def write_json(path, data):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


ORDER = ["title", "year", "runtime", "genres", "description", "source", "source_url"]


def ordered(info):
    out = {k: info[k] for k in ORDER if info.get(k) not in (None, "", [])}
    for k, v in info.items():
        if k not in out and v not in (None, "", []):
            out[k] = v
    return out


def process(item, kind, args, wiki):
    """item: video path (movie) or show folder. Returns (status, note, info)."""
    if kind == "movie":
        folder, fname = os.path.split(item)
        base = os.path.splitext(fname)[0]
        sidecar = os.path.join(folder, base + INFO_SUFFIX)
        poster_path = os.path.join(folder, base + ".jpg")
        need_poster = args.posters and not has_poster(folder, base)
        title, year = clean_title(fname)
    else:
        sidecar = os.path.join(item, SHOW_INFO)
        poster_path = os.path.join(item, "poster.jpg")
        need_poster = args.posters and not show_has_cover(os.path.dirname(item), item)
        title, year = clean_title(os.path.basename(item))

    exists = os.path.exists(sidecar)
    old = read_json(sidecar) if exists else None
    if exists and old is None and not args.overwrite:
        return "failed", "unreadable JSON, fix it or use --overwrite", {}
    # an existing sidecar without a description gets filled in by --online (fields it
    # already has are kept, so hand edits survive); --overwrite rebuilds it from scratch
    merge = exists and not args.overwrite
    if merge and not (args.online and (not old.get("description") or need_poster)):
        note = "has info" if not need_poster else "has info, --posters needs --online"
        return "skipped", note, old

    notes = []
    info = {"title": title}
    if year:
        info["year"] = year
    if kind == "movie" and not (merge and old.get("runtime")):
        rt = video_runtime_minutes(item)
        if rt:
            info["runtime"] = rt
        else:
            notes.append("runtime unknown")
    if merge:
        info.update(old)

    changed = not merge
    failed = False
    if args.online:
        try:
            extra, img, note = lookup(wiki, info.get("title") or title, info.get("year") or year, kind)
            notes.append(note)
            for k, v in extra.items():
                if k not in info:
                    info[k] = v
                    changed = True
            if need_poster:
                if img:
                    try:
                        notes.append(save_poster(wiki, img, poster_path))
                        changed = True
                    except Exception as e:      # noqa: BLE001 (bad image data, PIL errors)
                        notes.append("poster failed: %s" % e)
                        failed = True
                elif extra:
                    notes.append("no image on Wikipedia")
        except (urllib.error.URLError, OSError, ValueError) as e:
            notes.append("Wikipedia failed: %s" % e)
            failed = True
            if exists:
                # never replace a good sidecar with a worse one because the network hiccupped
                return "failed", "; ".join(notes) + " (kept the old file)", old or {}
            notes.append("wrote offline info, run --online again later")
    elif need_poster:
        notes.append("--posters needs --online")

    info = ordered(info)
    if merge and not changed:
        return ("failed" if failed else "skipped"), "; ".join(n for n in notes if n), info
    if not merge or info != ordered(old):
        write_json(sidecar, info)
    status = "failed" if failed else ("created" if not exists else "updated")
    return status, "; ".join(n for n in notes if n), info


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write <movie>.info.json sidecars for a Khan-Nomad SD card.")
    ap.add_argument("card", help="card folder (the one holding Movies/ and Shows/)")
    ap.add_argument("--online", action="store_true", help="add a description, year and genres from Wikipedia")
    ap.add_argument("--posters", action="store_true", help="download a poster where none exists (needs --online)")
    ap.add_argument("--lang", choices=["en", "tr"], default="en", help="Wikipedia language (default en)")
    ap.add_argument("--overwrite", action="store_true", help="rebuild sidecars that already exist")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    card = os.path.abspath(args.card)
    movies_dir = os.path.join(card, "Movies")
    shows_dir = os.path.join(card, "Shows")
    if not os.path.isdir(movies_dir) and not os.path.isdir(shows_dir):
        print("No Movies/ or Shows/ folder in %s" % card, file=sys.stderr)
        return 2
    if args.posters and not args.online:
        print("note: --posters only works together with --online", file=sys.stderr)

    wiki = Wiki(args.lang) if args.online else None
    work = []
    if os.path.isdir(movies_dir):
        work += [("movie", p) for p in find_movies(movies_dir)]
    if os.path.isdir(shows_dir):
        work += [("show", os.path.join(shows_dir, d)) for d in sorted(os.listdir(shows_dir), key=str.lower)
                 if visible(d) and os.path.isdir(os.path.join(shows_dir, d))]

    rows = []
    counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    for kind, item in work:
        label = os.path.relpath(item, card).replace(os.sep, "/")
        print("... %s" % label, flush=True)
        try:
            status, note, info = process(item, kind, args, wiki)
        except Exception as e:                  # noqa: BLE001 (keep going, report it)
            status, note, info = "failed", "%s: %s" % (type(e).__name__, e), {}
        counts[status] += 1
        rows.append((status, label, info.get("year") or "", info.get("runtime") or "", note))

    if not rows:
        print("No videos or show folders found.")
        return 0
    w = max(len(r[1]) for r in rows)
    w = min(max(w, 4), 48)
    print()
    print("%-8s  %-*s  %4s  %4s  %s" % ("status", w, "item", "year", "min", "note"))
    print("%s  %s  %s  %s  %s" % ("-" * 8, "-" * w, "-" * 4, "-" * 4, "-" * 4))
    for status, label, year, rt, note in rows:
        if len(label) > w:
            label = "…" + label[-(w - 1):]
        print("%-8s  %-*s  %4s  %4s  %s" % (status, w, label, year, rt, note))
    print()
    print("created %(created)d, updated %(updated)d, skipped %(skipped)d, failed %(failed)d" % counts
          + ("  (%d Wikipedia requests)" % wiki.requests if wiki else ""))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
