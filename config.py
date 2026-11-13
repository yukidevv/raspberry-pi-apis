"""共通設定: .env の読み込みと、環境変数からの設定値。

設定は環境変数のほか、このモジュールと同じフォルダの .env ファイル
からも読める（KEY=VALUE 形式）。両方ある場合は環境変数が優先される。
"""

import os


def _load_dotenv() -> None:
    # このモジュールと同じフォルダの .env があれば読み込む。
    # 既に設定されている環境変数は上書きしない（そちらが優先）。
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


_load_dotenv()

# 待ち受け。
HOST = os.environ.get("SUBTITLE_API_HOST", "0.0.0.0")
PORT = int(os.environ.get("SUBTITLE_API_PORT", "8787"))

# 認証トークン（エンドポイント群ごとに別々に照合する）。
# FX_TOKEN が未設定なら FxEmbed 中継は無効になる。
SUBTITLE_TOKEN = os.environ.get("SUBTITLE_API_TOKEN", "")
FX_TOKEN = os.environ.get("FX_API_TOKEN", "")
