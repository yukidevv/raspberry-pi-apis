# YouTube 字幕 API — Raspberry Pi セットアップ手順

自宅の Raspberry Pi で動かす単一目的の字幕 API。サーバ本体は
`subtitle_api.py`（Python 3 標準ライブラリのみ）で、字幕の取得には
yt-dlp を使う。設計上の制限として、受け付けるのは YouTube の動画 URL
だけにし、字幕テキストを整形して JSON で返す。それ以外のエンドポイント
やファイル参照は持たない。

## 構成（venv）

可搬性を重視し、実行環境は venv に閉じる。サーバの実行も yt-dlp も
venv 側でまかない、ホストの Python は venv を作る初回だけ使う。
サーバ本体は標準ライブラリのみで、追加パッケージは yt-dlp だけ。
Raspberry Pi OS（Debian 系）は PEP 668 でシステムへの pip install が
制限されている点でも、この形が無難。

```
~/subtitle-api/
├── subtitle_api.py
├── cookies.txt        （必要な場合のみ）
└── .venv/             （実行用の Python と yt-dlp）
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
3. venv の Python でサーバを起動する:

   ```
   SUBTITLE_API_TOKEN=<長いランダム文字列> \
   .venv/bin/python subtitle_api.py
   ```

   yt-dlp は、起動した Python と同じ venv 内のものが自動で使われる
   （別の場所の yt-dlp を使いたい場合だけ `YTDLP_BIN` で明示する）。
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
