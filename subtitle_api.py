#!/usr/bin/env python3
"""自宅 Raspberry Pi 用の、Muse 専用の小規模 API サーバ（入口）。

単一目的のエンドポイントを同じポートに同居させる。各エンドポイントは
自分の仕事しかししない:

- /subtitles: YouTube 字幕の取得（subtitles モジュール）。
- /x/...: FxEmbed（api.fxtwitter.com）への読み取り専用の中継
  （fx モジュール）。FX_API_TOKEN 未設定なら無効（503 を返す）。

このファイルは起動とルーティングだけを担い、設定は config
モジュールが .env と環境変数から読む。認証はエンドポイント群ごとに
別々のトークンで、X-Api-Token ヘッダ（または ?token=）で照合する。
ファイルアクセスなし、任意のコマンド実行なし。

使い方:
    SUBTITLE_API_TOKEN=<secret> python3 subtitle_api.py

    curl -H "X-Api-Token: <secret>" \
         "http://localhost:8787/subtitles?url=https://youtu.be/VIDEOID"

レスポンス JSON:
    {"video_id": "...", "lang": "ja", "text": "..."}
エラー時は {"error": ...} と 4xx/5xx ステータスを返す。
"""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import config
import fx
import subtitles


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

    def _raw(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token(self, qs: dict) -> str:
        return self.headers.get("X-Api-Token") or (qs.get("token") or [""])[0]

    def _fx(self, u, qs: dict):
        """FxEmbed への読み取り専用中継。中継先は固定の3形状だけ。"""
        if not config.FX_TOKEN:
            return self._json(503, {"error": "fx relay is not configured"})
        if self._token(qs) != config.FX_TOKEN:
            return self._json(401, {"error": "unauthorized"})
        try:
            upstream = fx.map_path(u.path, (qs.get("q") or [""])[0])
        except fx.RelayError as exc:
            return self._json(exc.status, {"error": exc.message})
        if upstream is None:
            return self._json(404, {"error": "not found"})
        try:
            status, body = fx.fetch(upstream)
        except RuntimeError as exc:
            return self._json(502, {"error": str(exc)})
        return self._raw(status, body)

    def _subtitles(self, qs: dict):
        if not config.SUBTITLE_TOKEN or self._token(qs) != config.SUBTITLE_TOKEN:
            return self._json(401, {"error": "unauthorized"})
        raw_url = (qs.get("url") or [""])[0]
        video_id = subtitles.extract_video_id(raw_url)
        if not video_id:
            return self._json(400, {"error": "url must be a YouTube video URL"})
        langs = (qs.get("langs") or ["en,ja"])[0]
        try:
            result = subtitles.fetch_subtitles(video_id, langs)
        except subprocess.TimeoutExpired:
            return self._json(504, {"error": "yt-dlp timed out"})
        except RuntimeError as exc:
            return self._json(502, {"error": str(exc)})
        if not result["text"]:
            return self._json(502, {"error": "subtitle track was empty"})
        return self._json(200, result)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json(200, {"ok": True})
        qs = parse_qs(u.query)
        if u.path.startswith("/x/"):
            return self._fx(u, qs)
        if u.path == "/subtitles":
            return self._subtitles(qs)
        return self._json(404, {"error": "not found"})

    do_POST = do_GET


if __name__ == "__main__":
    if not config.SUBTITLE_TOKEN:
        sys.exit("起動前に SUBTITLE_API_TOKEN を設定してください（未設定では起動しません）。")
    ThreadingHTTPServer((config.HOST, config.PORT), Handler).serve_forever()
