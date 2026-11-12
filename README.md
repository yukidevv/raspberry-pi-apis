# YouTube subtitle API — Pi setup notes

Draft prepared 2026-11-12. Server: `subtitle_api.py` (Python 3 stdlib only,
plus `yt-dlp` on the Pi). Single-purpose by design: it accepts only YouTube
video URLs, fetches subtitles with yt-dlp, returns cleaned text as JSON.
No filesystem browsing, no other endpoints.

## On the Pi

1. Copy `subtitle_api.py` to the Pi (e.g. `~/subtitle-api/`).
2. Make sure `yt-dlp` is available (`yt-dlp --version`).
3. Start it with a token:
   `SUBTITLE_API_TOKEN=<long-random-string> python3 subtitle_api.py`
   (port 8787 by default; `SUBTITLE_API_PORT` to change)
4. If subtitle downloads fail with bot-check errors, export `cookies.txt`
   from a logged-in YouTube session and place it next to the script —
   it is picked up automatically.

## Still to decide: how Muse reaches it

- **Cloudflare Tunnel** — no Tailscale join needed; Pi dials out, Muse
  calls the tunnel URL + token.
- **Tailscale** — private, but the VM's tailnet join approval is still
  outstanding from the earlier attempt.

Either way the server itself does not change; only the exposure route does.

## Verified in the VM (2026-11-12)

- `GET /health` → 200 `{"ok": true}`
- No/wrong token → 401
- Token + non-YouTube URL → 400
- Actual subtitle fetching is untested from the VM (YouTube returns 429
  there — that is the whole reason this runs on the Pi's home connection).
