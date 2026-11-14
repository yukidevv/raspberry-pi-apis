# Raspberry Pi APIs — セットアップ手順

自宅の Raspberry Pi で動かす、Muse 専用の小規模 API サーバ。サーバ
本体は Python 3 標準ライブラリのみで、入口の `subtitle_api.py` と
config / subtitles / fx の各モジュールからなる。字幕の取得には
yt-dlp を使う。単一目的のエンドポイントを同じポートに同居させる
構成で、各エンドポイントは自分の仕事しかしない。字幕取得は YouTube の
動画 URL だけを受け付け、字幕テキストを整形して JSON で返す。FxEmbed
中継は読み取り専用で、中継先は固定したパスの形状だけに限る。ファイル
参照のエンドポイントは持たない。

## 構成（venv）

可搬性を重視し、実行環境は venv に閉じる。サーバの実行も yt-dlp も
venv 側でまかない、ホストの Python は venv を作る初回だけ使う。
サーバ本体は標準ライブラリのみで、追加パッケージは yt-dlp だけ。
Raspberry Pi OS（Debian 系）は PEP 668 でシステムへの pip install が
制限されている点でも、この形が無難。

```
~/subtitle-api/
├── subtitle_api.py    （入口: 起動とルーティング）
├── config.py          （.env 読み込みと共通設定）
├── subtitles.py       （字幕取得）
├── fx.py              （FxEmbed 中継）
├── .env               （任意の設定。repo には入れない）
├── cookies.txt        （必要な場合のみ）
└── .venv/             （実行用の Python と yt-dlp）
```

## Pi でのセットアップ

1. 4つの `.py` ファイルを Pi の `~/subtitle-api/` に置く
   （モジュール同士が import するため、同じフォルダに揃える）。
2. venv を作って yt-dlp を入れる:

   ```
   cd ~/subtitle-api
   python3 -m venv .venv
   .venv/bin/pip install -U yt-dlp
   ```

   yt-dlp の更新は `.venv/bin/pip install -U yt-dlp` を再実行するだけ。
3. 設定が必要な場合は `.env` に書く（スクリプトと同じフォルダに
   置くと起動時に自動で読まれる）。待ち受けホストやポートを変える
   場合のみで、必須の設定はない:

   ```
   # .env の中身（例）
   SUBTITLE_API_HOST=127.0.0.1
   ```

   環境変数で直接渡してもよく、その場合は環境変数が優先される。
4. venv の Python でサーバを起動する:

   ```
   .venv/bin/python subtitle_api.py
   ```

   yt-dlp は、起動した Python と同じ venv 内のものが自動で使われる
   （別の場所の yt-dlp を使いたい場合だけ `YTDLP_BIN` で明示する）。
   ポートは既定 8787（`SUBTITLE_API_PORT` で変更可）。
   リバースプロキシの後ろで動かす場合は `SUBTITLE_API_HOST=127.0.0.1`
   を指定し、待ち受けをローカルホストだけにする。
5. 字幕のダウンロードが bot チェックで失敗する場合は、ログイン済みの
   YouTube セッションから cookies.txt をエクスポートして、スクリプトと
   同じフォルダに置く。自動で使われる。

## エンドポイント

アプリレベルの認証はない。到達制御は Tailscale（参加できる端末の
制限）と、玄関の Apache の `Require` で行う前提の設計。

- `GET /health` — `{"ok": true}` を返す。
- `GET /subtitles?url=<YouTube URL>&langs=<言語コード>` — 字幕取得。
- `GET /x/status/<ツイートID>` — FxEmbed の単一ポスト取得を中継。
- `GET /x/profile/<ハンドル>/statuses` — FxEmbed のアカウント
  タイムライン取得を中継。
- `GET /x/search?q=<検索語>` — FxEmbed のキーワード検索を中継。

## 接続ルート

Muse からこの API への経路は Tailscale に決まった（2026-11-14
運用開始）。Pi の Apache を玄関として `/api/` 配下をこのサーバへ
プロキシし、到達できるのは tailnet 参加端末からのみ。公開側の
`/api/` は閉じている。

## VM での検証結果（2026-11-12）

- `GET /health` → 200 `{"ok": true}`
- トークンなし・誤ったトークン → 401
- トークン＋YouTube 以外の URL → 400
- 実際の字幕取得は VM からは未検証（YouTube が 429 を返すためで、
  それこそが Pi の自宅回線で動かす理由）
