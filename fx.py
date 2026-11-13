"""FxEmbed 中継: api.fxtwitter.com への読み取り専用の薄い中継。

中継先は固定した3形状のパスだけに限り、任意 URL のプロキシには
ならない。上流のステータスと本文はそのまま返す。
"""

import re
import urllib.error
import urllib.request
from urllib.parse import quote

UPSTREAM = "https://api.fxtwitter.com"
TIMEOUT = 20
STATUS_RE = re.compile(r"^/x/status/(\d{1,25})$")
PROFILE_RE = re.compile(r"^/x/profile/([A-Za-z0-9_]{1,15})/statuses$")


class RelayError(Exception):
    """HTTP ステータス付きで中継を中断する。"""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def map_path(path: str, q: str) -> str | None:
    """公開パスを上流パスへ対応づける。

    対象外のパスなら None、検索語の不備は RelayError（400）を送出する。
    """
    m = STATUS_RE.match(path)
    if m:
        return f"/2/status/{m.group(1)}"
    m = PROFILE_RE.match(path)
    if m:
        return f"/2/profile/{m.group(1)}/statuses"
    if path == "/x/search":
        if not q or len(q) > 500:
            raise RelayError(400, "q is required (max 500 chars)")
        return f"/2/search?q={quote(q, safe='')}"
    return None


def fetch(upstream_path: str) -> tuple[int, bytes]:
    """FxEmbed の固定パスへ GET し、ステータスと本文をそのまま返す。"""
    req = urllib.request.Request(
        UPSTREAM + upstream_path,
        headers={"Accept": "application/json", "User-Agent": "pi-api-relay/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # 上流のエラー応答もステータスと本文をそのまま中継する。
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"fx upstream unreachable: {exc.reason}") from exc
