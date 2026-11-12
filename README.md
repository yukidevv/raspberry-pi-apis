# YouTube 字幕 API — Raspberry Pi セットアップ手順

自宅の Raspberry Pi で動かす単一目的の字幕 API。サーバ本体は
`subtitle_api.py`（Python 3 標準ライブラリのみ）で、字幕の取得には
yt-dlp を使う。設計上の制限として、受け付けるのは YouTube の動画 URL
だけにし、字幕テキストを整形して JSON で返す。それ以外のエンドポイント
やファイル参照は持たない。

## 構成（venv）

サーバ本体に venv は不要（標準ライブラリのみ）。venv は yt-dlp の隔離と
更新のために使う。Raspberry Pi OS（Debian 系）は PEP 668 でシステムへの
pip install が制限されているため、この形が無難。

```
~/subtitle-api/
├── subtitle_api.py
├── cookies.txt        （必要な場合のみ）
└── .venv/             （yt-dlp 専用）
```

## Pi でのセットアップ

1. `subtitle_api.py` を Pi の `~/subtitle-api/` に置く。
2. venv を作って yt-dlp を入れる:

   ```
   cd ~/subtitle-api
   python3 -m venv .venv
   .venv/bin/pip install -U yt-dlp
   ```

   yt-dlp の更新は `.venv/bin/pip install -U yt-dlp` を再実行するだけ。
3. トークンと yt-dlp のパスを指定して起動する:

   ```
   SUBTITLE_API_TOKEN=<長いランダム文字列> \
   YTDLP_BIN=$HOME/subtitle-api/.venv/bin/yt-dlp \
   python3 subtitle_api.py
   ```

   ポートは既定 8787（`SUBTITLE_API_PORT` で変更可）。
4. 字幕のダウンロードが bot チェックで失敗する場合は、ログイン済みの
   YouTube セッションから cookies.txt をエクスポートして、スクリプトと
   同じフォルダに置く。自動で使われる。

## 公開ルート（未決定）

Muse からこの API に届く経路は2案あり、どちらにするかは未決定。
サーバ自体はどちらの場合も同じ。

- **Cloudflare Tunnel** — Tailscale 参加は不要。Pi から外向きに接続し、
  Muse はトンネルの URL＋トークンで呼ぶ。
- **Tailscale** — プライベートだが、VM の tailnet 参加の承認が前回の
  試行から未完了のまま。

## VM での検証結果（2026-11-12）

- `GET /health` → 200 `{"ok": true}`
- トークンなし・誤ったトークン → 401
- トークン＋YouTube 以外の URL → 400
- 実際の字幕取得は VM からは未検証（YouTube が 429 を返すためで、
  それこそが Pi の自宅回線で動かす理由）
