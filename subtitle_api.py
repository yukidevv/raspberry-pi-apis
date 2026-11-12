#!/usr/bin/env python3
"""自宅 Raspberry Pi 用の単一目的 YouTube 字幕 API。

YouTube の URL を受け取り、yt-dlp で字幕を取得して、整形したプレーン
テキストを返す。それ以外のことはしない: ファイルアクセスなし、任意の
コマンド実行なし、他のホストへの接続なし。認証は X-Api-Token ヘッダ
（または ?token=）によるトークン認証。

使い方:
    SUBTITLE_API_TOKEN=<secret> python3 subtitle_api.py [--port 8787]

    curl -H "X-Api-Token: <secret>" \
         "http://localhost:8787/subtitles?url=https://youtu.be/VIDEOID"

任意: 字幕のダウンロードが bot チェックで失敗する場合は、ログイン済み
YouTube セッションからエクスポートした cookies.txt をこのファイルと
同じフォルダに置くこと。あれば自動で yt-dlp に渡される。

レスポンス JSON:
    {"video_id": "...", "lang": "ja", "title": "...", "text": "..."}
エラー時は {"error": ...} と 4xx/5xx ステータスを返す。
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
HOST = os.environ.get("SUBTITLE_API_HOST", "0.0.0.0")
PORT = int(os.environ.get("SUBTITLE_API_PORT", "8787"))
HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, "cookies.txt")
def _default_ytdlp() -> str:
    # venv の Python で起動された場合は、同じ venv 内の yt-dlp を使う。
    candidate = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    return candidate if os.path.exists(candidate) else "yt-dlp"


YTDLP = os.environ.get("YTDLP_BIN") or _default_ytdlp()
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
    """VTT のヘッダ、タイムスタンプ、タグ、重複するロール行を取り除く。"""
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
        # 手動字幕と自動字幕の両方が保存された場合は手動字幕を優先する。
        # ファイル名は <id>.<lang>.vtt 形式。要求された言語の最初の一致を使う。
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
    def log_message(self, fmt, *args):  # エラー以外は標準出力を静かに保つ
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
        sys.exit("起動前に SUBTITLE_API_TOKEN を設定してください（未設定では起動しません）。")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
