#!/usr/bin/env python3
"""Single-purpose YouTube subtitle API for the home Raspberry Pi.

Accepts a YouTube URL, fetches subtitles with yt-dlp, and returns cleaned
plain text. Nothing else: no file access, no arbitrary commands, no other
hosts. Token authentication via the X-Api-Token header (or ?token=).

Usage:
    SUBTITLE_API_TOKEN=<secret> python3 subtitle_api.py [--port 8787]

    curl -H "X-Api-Token: <secret>" \
         "http://localhost:8787/subtitles?url=https://youtu.be/VIDEOID"

Optional: place a cookies.txt (exported from a logged-in YouTube session)
next to this file if subtitle downloads start failing with bot checks;
it is passed to yt-dlp automatically when present.

Response JSON:
    {"video_id": "...", "lang": "ja", "title": "...", "text": "..."}
Errors are JSON with an "error" field and a 4xx/5xx status.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = os.environ.get("SUBTITLE_API_TOKEN", "")
PORT = int(os.environ.get("SUBTITLE_API_PORT", "8787"))
HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, "cookies.txt")
YTDLP = os.environ.get("YTDLP_BIN", "yt-dlp")
TIMEOUT = 120

YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtu.be",
}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url: str) -> str | None:
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or (u.hostname or "") not in YOUTUBE_HOSTS:
        return None
    if u.hostname and u.hostname.endswith("youtu.be"):
        vid = u.path.lstrip("/").split("/")[0]
        return vid if VIDEO_ID_RE.match(vid) else None
    qs = parse_qs(u.query)
    if u.path == "/watch" and qs.get("v"):
        vid = qs["v"][0]
        return vid if VIDEO_ID_RE.match(vid) else None
    m = re.match(r"^/(shorts|live|embed)/([A-Za-z0-9_-]{11})", u.path)
    return m.group(2) if m else None


def clean_vtt(raw: str) -> str:
    """Strip VTT headers, timestamps, tags and duplicate rolling lines."""
    lines, seen = [], set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def fetch_subtitles(video_id: str, langs: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(id)s.%(ext)s")
        cmd = [
            YTDLP, "--skip-download", "--write-subs", "--write-auto-subs",
            "--sub-langs", langs, "--sub-format", "vtt/best",
            "--no-warnings", "-o", out, url,
        ]
        if os.path.exists(COOKIES):
            cmd[1:1] = ["--cookies", COOKIES]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        files = sorted(f for f in os.listdir(tmp) if f.endswith(".vtt"))
        if not files:
            detail = (proc.stderr or proc.stdout or "").strip()[-500:]
            raise RuntimeError(f"no subtitles found: {detail}")
        # Prefer a manual track over auto-generated when yt-dlp saved both:
        # file names are <id>.<lang>.vtt; just take the first requested lang.
        chosen = files[0]
        for want in langs.split(","):
            match = [f for f in files if f".{want}." in f]
            if match:
                chosen = match[0]
                break
        with open(os.path.join(tmp, chosen), encoding="utf-8") as fh:
            text = clean_vtt(fh.read())
        lang = chosen.rsplit(".", 2)[-2] if chosen.count(".") >= 2 else ""
        return {"video_id": video_id, "lang": lang, "text": text}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep stdout quiet except errors
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json(200, {"ok": True})
        if u.path != "/subtitles":
            return self._json(404, {"error": "not found"})
        qs = parse_qs(u.query)
        token = self.headers.get("X-Api-Token") or (qs.get("token") or [""])[0]
        if not TOKEN or token != TOKEN:
            return self._json(401, {"error": "unauthorized"})
        raw_url = (qs.get("url") or [""])[0]
        video_id = extract_video_id(raw_url)
        if not video_id:
            return self._json(400, {"error": "url must be a YouTube video URL"})
        langs = (qs.get("langs") or ["ja,en.*"])[0]
        try:
            result = fetch_subtitles(video_id, langs)
        except subprocess.TimeoutExpired:
            return self._json(504, {"error": "yt-dlp timed out"})
        except RuntimeError as exc:
            return self._json(502, {"error": str(exc)})
        if not result["text"]:
            return self._json(502, {"error": "subtitle track was empty"})
        return self._json(200, result)

    do_POST = do_GET


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("Set SUBTITLE_API_TOKEN before starting (refusing to run open).")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
