#!/usr/bin/env python3
"""Fake Nomad: run the Nomad web interface on a laptop, no ESP32 needed.

Serves a folder laid out like a Nomad SD card and answers the same HTTP API the
firmware does (/listfiles, /api/index, /media, range requests, admin status...),
so the real pages from SD_Card_Template work in a normal browser.

Usage:
    python fake_nomad.py                 # http://localhost:8080, card = ./card
    python fake_nomad.py --card D:\\      # serve a real SD card / any folder
    python fake_nomad.py --lan           # also reachable from phones on your WiFi

On first run ./card is created as a copy of SD_Card_Template, so writes from the
admin page (themes, uploads, deletes) never touch the template in the repo.

Standard library only. Formats follow firmware/JcorpNomadProject/JcorpNomadProject.ino.
"""

import argparse
import email.parser
import email.policy
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "..", "SD_Card_Template"))

# Short page aliases the firmware registers ("/movies" -> "/movies.html")
PAGE_ALIASES = {
    "movies": "movies.html", "music": "music.html", "playlist": "playlist.html",
    "books": "books.html", "shows": "shows.html", "admin": "admin.html",
    "games": "games.html", "maps": "maps.html", "menu": "menu.html",
    "gallery": "gallery.html", "archive": "archive.html", "files": "files.html",
    "filebrowser": "filebrowser.html", "comic": "comics.html", "comics": "comics.html",
    "translate": "translate.html", "chat": "chat.html", "epub": "epub.html",
    "pdf": "pdf.html", "songs": "songs.html", "queue": "queue.html",
    "cookbook": "cookbook.html", "workshop": "workshop.html",
    "theme-ui": "theme-customization-ui.html",
}

EXTRA_MIME = {
    ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm",
    ".epub": "application/epub+zip", ".cbz": "application/vnd.comicbook+zip",
    ".zim": "application/octet-stream", ".vtt": "text/vtt", ".srt": "text/plain",
    ".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".flac": "audio/flac",
    ".ndjson": "application/x-ndjson", ".json": "application/json", ".svg": "image/svg+xml",
    ".webp": "image/webp", ".m3u": "audio/x-mpegurl",
}

DEFAULT_SETTINGS = {
    "rgbMode": "off", "rgbColor": "#ff0000", "adminPassword": "", "adminPasswordSet": False,
    "wifiSSID": "Khan-Nomad", "wifiPassword": "password", "brightness": 100,
    "autoGenerateMedia": True, "flipScreen": False, "dlnaEnabled": True, "dnsCatchAll": False,
}

FAKE_CARD_TOTAL = 128 * 1000**3  # pretend the card is 128 GB


class FakeNomad:
    def __init__(self, card):
        self.card = os.path.abspath(card)
        self.settings = dict(DEFAULT_SETTINGS)
        self.logs = []
        self.log("info", "Fake Nomad started, card: " + self.card)

    def log(self, kind, msg):
        self.logs.append({"message": msg, "type": kind, "timestamp": int(time.time() * 1000)})
        del self.logs[:-50]  # firmware keeps the last 50

    def disk(self, card_path):
        """Card path ("/Movies/a.mp4") -> real path, or None if it escapes the card."""
        card_path = unquote(card_path or "/").replace("\\", "/")
        if ".." in card_path.split("/"):
            return None
        real = os.path.normpath(os.path.join(self.card, card_path.lstrip("/")))
        if real != self.card and not real.startswith(self.card + os.sep):
            return None
        return real


def norm_path(p):
    p = "/" + (p or "").strip().strip("/")
    return re.sub(r"/+", "/", p)


def mime_for(path):
    ext = os.path.splitext(path)[1].lower()
    return EXTRA_MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def index_depth(path):
    # same rules as the firmware: root and every Books level are flat, the rest recurse
    if path == "/" or path == "/Books" or path.startswith("/Books/"):
        return 0
    return 10


def build_index(nomad, path):
    """NDJSON like /.system-index/*.ndjson: header line, then one entry per item."""
    real = nomad.disk(path)
    lines = []
    max_depth = index_depth(path)

    def walk(card_dir, real_dir, depth):
        if depth > max_depth:
            return
        try:
            names = sorted(os.listdir(real_dir), key=str.lower)
        except OSError:
            return
        for name in names:
            if name.startswith("."):
                continue
            full_real = os.path.join(real_dir, name)
            full_card = (card_dir.rstrip("/") + "/" + name)
            if os.path.isdir(full_real):
                entry = {"t": "d", "n": name, "p": full_card}
                if full_card.startswith("/Books/") and is_comic_folder(full_real):
                    entry["comic"] = True
                lines.append(entry)
                walk(full_card, full_real, depth + 1)
            else:
                lines.append({"t": "f", "n": name, "p": full_card,
                              "sz": os.path.getsize(full_real), "mt": 0})

    if real and os.path.isdir(real):
        walk(path, real, 0)
    header = {"_type": "dir", "path": path, "sig": "%016x" % (hash(path) & 0xFFFFFFFFFFFFFFFF),
              "count": len(lines)}
    return header, lines


def is_comic_folder(real_dir):
    try:
        imgs = [n for n in os.listdir(real_dir) if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    except OSError:
        return False
    return len(imgs) >= 2


class Handler(BaseHTTPRequestHandler):
    server_version = "FakeNomad/1.0"
    protocol_version = "HTTP/1.1"
    nomad: FakeNomad = None

    # ---------- helpers ----------
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, self.path[:120]))

    def send_bytes(self, body, ctype="application/json", status=200, headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, obj, status=200):
        self.send_bytes(json.dumps(obj), "application/json", status)

    def send_text(self, text, status=200):
        self.send_bytes(text, "text/plain", status)

    def form(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("multipart/form-data"):
            msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
                b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw)
            fields, files = {}, []
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                data = part.get_payload(decode=True) or b""
                if filename:
                    files.append((name, filename, data))
                else:
                    fields[name] = data.decode("utf-8", "replace")
            return fields, files, raw
        if "json" in ctype:
            try:
                return json.loads(raw or b"{}"), [], raw
            except ValueError:
                return {}, [], raw
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}, [], raw

    # ---------- file serving with Range ----------
    def serve_file(self, real, page=False):
        size = os.path.getsize(real)
        ctype = mime_for(real)
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        # always revalidate: this is for editing the interface, so changes must show on reload
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(real, "rb") as f:
            f.seek(start)
            left = length
            try:
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass  # browser seeked or closed the player, normal for video

    def serve_card_path(self, card_path):
        real = self.nomad.disk(card_path)
        if real and os.path.isdir(real):
            real = os.path.join(real, "index.html")
        if not real or not os.path.isfile(real):
            return self.send_text("File not found", 404)
        self.serve_file(real)

    # ---------- GET / HEAD ----------
    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type, Accept, X-Admin-Token")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        n = self.nomad

        if path == "/":
            return self.serve_card_path("/index.html")
        alias = PAGE_ALIASES.get(path.strip("/"))
        if alias:
            return self.serve_card_path("/" + alias)

        if path == "/listfiles":
            return self.api_listfiles(q.get("dir"))
        if path == "/api/index":
            header, lines = build_index(n, norm_path(q.get("path", "/")))
            body = "\n".join(json.dumps(x) for x in [header] + lines) + "\n"
            return self.send_bytes(body, "application/x-ndjson")
        if path == "/api/index-nested":
            p = norm_path(q.get("path", "/"))
            _, lines = build_index(n, p)
            return self.send_json({"status": "ready", "path": p, "entries": lines})
        if path == "/media":
            return self.serve_card_path(q.get("file", ""))
        if path == "/api/ui-config":
            real = n.disk("/.system-ui.json")
            if real and os.path.isfile(real):
                return self.serve_file(real)
            return self.send_json({})
        if path in ("/api/archive-list", "/zim-list"):
            return self.send_json({"archives": self.archive_list()})
        if path == "/api/games-list":
            return self.send_json({"games": self.games_list()})
        if path == "/api/maps-list":
            return self.send_json({"regions": self.maps_list()})
        if path == "/admin-status":
            return self.send_json({"ssid": n.settings["wifiSSID"], "wifiPassword": "__set__",
                                   "users": 1, "wifiMode": "ap", "ip": self.headers.get("Host", "")})
        if path == "/scan-status":
            return self.send_json({"status": "Idle", "mode": "\u2014", "queueDepth": 0, "currentPath": "",
                                   "sdScanInProgress": False, "indexingInProgress": False,
                                   "indexingTasksActive": False, "requestIndexing": False,
                                   "progressPercent": 100, "currentBucketNum": 0, "totalBuckets": 0})
        if path == "/cpu-temp":
            return self.send_json({"temperature": 41.5})
        if path == "/sdinfo":
            used = self.card_usage()[0]
            return self.send_json({"total": FAKE_CARD_TOTAL, "used": used, "statTrusted": True})
        if path == "/api/sd-breakdown":
            return self.send_json({"scanning": False, "breakdown": self.breakdown()})
        if path == "/console-logs":
            return self.send_json({"logs": n.logs})
        if path == "/settings":
            s = dict(n.settings)
            s["adminPassword"] = "__set__" if s["adminPassword"] else ""
            s["adminPasswordSet"] = bool(n.settings["adminPassword"])
            return self.send_json(s)
        if path in ("/playlist.m3u", "/nomad.m3u"):
            return self.playlist()
        if path in ("/api/wifi-mode",):
            return self.send_json({"mode": "ap", "staSSID": "", "staPersist": False, "connected": False})
        if path in ("/api/wifi-scan",):
            return self.send_json({"networks": []})
        if path in ("/api/performance", "/api/tasks"):
            return self.send_json({})
        if path == "/assets/check":
            real = n.disk(q.get("file", ""))
            return self.send_json({"file": q.get("file", ""), "exists": bool(real and os.path.exists(real))})
        if path in ("/generate_204", "/hotspot-detect.html"):
            return self.serve_card_path("/index.html")

        # anything that looks like a file comes off the "card"
        real = n.disk(path)
        if real and (os.path.isfile(real) or os.path.isfile(os.path.join(real, "index.html"))):
            return self.serve_card_path(path)
        if "." in os.path.basename(path):
            return self.send_text("File not found", 404)
        # unknown non-file route: the firmware's captive portal sends the landing page
        return self.serve_card_path("/index.html")

    # ---------- POST ----------
    def do_POST(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        n = self.nomad
        fields, files, raw = self.form()

        if path == "/save":
            real = n.disk(fields.get("filename", ""))
            if not fields.get("filename") or not real or "content" not in fields:
                return self.send_text("Missing parameters", 400)
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, "w", encoding="utf-8", newline="") as f:
                f.write(fields["content"])
            n.log("info", "Saved " + fields["filename"])
            return self.send_text("OK")
        if path == "/mkdir":
            real = n.disk(fields.get("dirname", ""))
            if not real:
                return self.send_text("Invalid path", 400)
            os.makedirs(real, exist_ok=True)
            return self.send_text("OK")
        if path == "/delete":
            real = n.disk(fields.get("filename", ""))
            if not real or real == n.card or not os.path.exists(real):
                return self.send_text("Not found", 404)
            shutil.rmtree(real) if os.path.isdir(real) else os.remove(real)
            n.log("info", "Deleted " + fields["filename"])
            return self.send_text("OK")
        if path == "/rename":
            old, new = n.disk(fields.get("oldname", "")), n.disk(fields.get("newname", ""))
            if not old or not new or not os.path.exists(old):
                return self.send_text("Invalid path", 400)
            os.rename(old, new)
            return self.send_text("OK")
        if path == "/upload":
            d = norm_path(fields.get("dir", "/"))
            saved = []
            for _, filename, data in files:
                real = n.disk(d + "/" + os.path.basename(filename))
                if not real:
                    return self.send_json({"error": "Invalid path"}, 400)
                os.makedirs(os.path.dirname(real), exist_ok=True)
                with open(real, "wb") as f:
                    f.write(data)
                saved.append(filename)
            n.log("info", "Uploaded %s to %s" % (", ".join(saved), d))
            return self.send_json({"status": "ok", "files": saved})
        if path == "/auth/login":
            body = fields.get("body")
            try:
                pw = json.loads(body).get("password", "") if body else fields.get("password", "")
            except ValueError:
                pw = ""
            if n.settings["adminPassword"] and pw != n.settings["adminPassword"]:
                return self.send_json({"error": "Invalid password"}, 401)
            return self.send_json({"token": "fake-nomad-session"})
        if path == "/settings":
            data = fields
            if "body" in fields:
                try:
                    data = json.loads(fields["body"])
                except ValueError:
                    data = {}
            for k, v in data.items():
                if k in n.settings and v != "__set__":
                    n.settings[k] = v
            n.log("info", "Settings updated")
            return self.send_json({"status": "ok"})
        if path == "/api/ui-config":
            # admin posts form-encoded body=<json>; accept raw JSON too
            body = fields.get("body") if isinstance(fields, dict) and "body" in fields else raw.decode("utf-8", "replace")
            try:
                json.loads(body)
            except ValueError:
                return self.send_json({"error": "Invalid JSON"}, 400)
            with open(n.disk("/.system-ui.json"), "w", encoding="utf-8") as f:
                f.write(body)
            return self.send_json({"status": "ok"})
        # everything else (reindex, restart, LEDs, brightness...) just succeeds
        n.log("info", "Ignored (fake): " + path)
        return self.send_json({"status": "ok", "fake": True})

    # ---------- API bodies ----------
    def api_listfiles(self, d):
        if d is None:
            return self.send_json({"error": "Missing 'dir' parameter"}, 400)
        real = self.nomad.disk(d)
        if not real or not os.path.isdir(real):
            return self.send_json({"error": "Directory not found"}, 404)
        out = []
        for name in sorted(os.listdir(real), key=str.lower):
            full = os.path.join(real, name)
            if os.path.isdir(full):
                out.append({"name": name + "/", "size": 0, "isDir": True})
            else:
                out.append({"name": name, "size": os.path.getsize(full), "isDir": False})
        return self.send_json(out)

    def list_dir(self, card_dir):
        real = self.nomad.disk(card_dir)
        if not real or not os.path.isdir(real):
            return []
        return sorted(os.listdir(real), key=str.lower)

    def archive_list(self):
        groups = {}
        for name in self.list_dir("/Archive"):
            real = self.nomad.disk("/Archive/" + name)
            if name.startswith(".") or os.path.isdir(real):
                continue
            low = name.lower()
            split = bool(re.search(r"\.zim[a-z]{2}$", low))
            if low.endswith(".zim") or split:
                typ = "zim"
            elif low.endswith(".mbtiles"):
                typ = "maps"
            elif low.endswith((".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".md", ".z64")):
                typ = "rom"
            else:
                typ = "file"
            gid = name[:-6] if split else os.path.splitext(name)[0]
            g = groups.setdefault(gid, {"id": gid, "name": gid, "type": typ, "split": split,
                                        "totalSize": 0, "parts": []})
            size = os.path.getsize(real)
            g["parts"].append({"path": "/Archive/" + name, "size": size})
            g["totalSize"] += size
            g["split"] = g["split"] or split
        return list(groups.values())

    def games_list(self):
        out = []
        for name in self.list_dir("/Games"):
            real = self.nomad.disk("/Games/" + name)
            low = name.lower()
            if name.startswith(".") or os.path.isdir(real) or low.endswith((".png", ".jpg", ".jpeg")):
                continue
            out.append({"name": name, "path": "/Games/" + name, "size": os.path.getsize(real)})
        return out

    def maps_list(self):
        out = []
        for name in self.list_dir("/Maps"):
            manifest = "/Maps/%s/manifest.json" % name
            real = self.nomad.disk(manifest)
            if real and os.path.isfile(real):
                out.append({"id": name, "manifest": manifest})
        return out

    def card_usage(self):
        total = files = 0
        for root, _, names in os.walk(self.nomad.card):
            for nm in names:
                try:
                    total += os.path.getsize(os.path.join(root, nm))
                    files += 1
                except OSError:
                    pass
        return total, files

    def breakdown(self):
        out = []
        for name in self.list_dir("/"):
            real = self.nomad.disk("/" + name)
            if not os.path.isdir(real):
                continue
            b = f = d = 0
            for root, dirs, names in os.walk(real):
                d += len(dirs)
                for nm in names:
                    try:
                        b += os.path.getsize(os.path.join(root, nm))
                        f += 1
                    except OSError:
                        pass
            out.append({"dir": "/" + name, "bytes": b, "files": f, "dirs": d})
        return sorted(out, key=lambda e: -e["bytes"])

    def playlist(self):
        host = self.headers.get("Host", "localhost")
        lines = ["#EXTM3U"]
        for bucket, exts in (("/Movies", (".mp4", ".m4v", ".webm", ".mkv")),
                             ("/Music", (".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wav"))):
            lines.append("# === %s ===" % bucket.strip("/").upper())
            _, entries = build_index(self.nomad, bucket)
            for e in entries:
                if e["t"] == "f" and e["n"].lower().endswith(exts):
                    lines.append("#EXTINF:-1,%s" % os.path.splitext(e["n"])[0])
                    lines.append("http://%s%s" % (host, quote(e["p"])))
        return self.send_bytes("\n".join(lines) + "\n", "audio/x-mpegurl")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Run the Nomad web interface on your computer.")
    ap.add_argument("--card", default=os.path.join(HERE, "card"),
                    help="folder laid out like a Nomad SD card (default: ./card, copied from SD_Card_Template)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--lan", action="store_true", help="listen on all interfaces so phones can connect")
    args = ap.parse_args()

    card = os.path.abspath(args.card)
    if not os.path.isdir(card):
        if card != os.path.abspath(os.path.join(HERE, "card")):
            sys.exit("Card folder not found: " + card)
        print("Creating %s from SD_Card_Template ..." % card)
        shutil.copytree(TEMPLATE, card)

    Handler.nomad = FakeNomad(card)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    httpd = ThreadingHTTPServer((host, args.port), Handler)
    print("Fake Nomad is running. Card: " + card)
    print("  Open: http://localhost:%d" % args.port)
    if args.lan and lan_ip():
        print("  From a phone on the same WiFi: http://%s:%d" % (lan_ip(), args.port))
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
