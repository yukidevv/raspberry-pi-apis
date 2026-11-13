"""字幕取得: YouTube の URL から yt-dlp で字幕を取り、整形して返す。

任意: 字幕のダウンロードが bot チェックで失敗する場合は、ログイン済み
YouTube セッションからエクスポートした cookies.txt をこのファイルと
同じフォルダに置くこと。あれば自動で yt-dlp に渡される。
"""

import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

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
