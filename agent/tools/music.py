"""
Spotify playback: turn a song name into a track and start it in the desktop app.

The desktop app plays a specific song only via `spotify:track:<id>`, so this
module resolves the id first:
  1. open.spotify.com/search rendered with headless Playwright (no login needed)
  2. DuckDuckGo web search as a backup (fast, but sometimes CAPTCHA'd)
  3. every candidate is checked against the track's oEmbed title
  4. `spotify:track:<id>` handed to the OS handler -> Spotify plays it

If nothing resolves, it falls back to `spotify:search:<query>` inside the app.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..registry import ToolError, register

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

_STOPWORDS = {
    "the", "a", "an", "of", "official", "video", "audio", "lyrics", "live",
    "remix", "feat", "ft", "free", "download", "hd", "4k", "song", "by",
    "on", "in", "and",
}

_TRACK_ID = r"(?:open\.spotify\.com/track/|spotify:track:)([A-Za-z0-9]{22})"

# Titles that are almost never the song the user asked for.
_COVER_TERMS = (
    "karaoke", "instrumental", "backing version", "made popular by",
    "cover", "sped up", "nightcore", "8 bit", "8-bit", "ringtone",
)

# query -> (track_id, title, expiry); keeps repeat requests instant.
_CACHE: Dict[str, Tuple[str, Optional[str], float]] = {}
_CACHE_TTL = 1800.0


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def _tokens(text: str) -> set:
    return {
        t for t in re.findall(r"[a-z0-9']+", (text or "").lower())
        if t not in _STOPWORDS and len(t) > 1
    }


def _match_score(wanted: set, title: Optional[str]) -> float:
    if not wanted or not title:
        return 0.0
    score = len(wanted & _tokens(title)) / len(wanted)
    low = title.lower()
    if any(term in low for term in _COVER_TERMS):
        score *= 0.6
    return score


def _spotify_search_ids(query: str, limit: int = 6) -> List[str]:
    """Track ids from open.spotify.com/search, rendered headless (no login)."""
    import asyncio

    from playwright.async_api import async_playwright

    url = "https://open.spotify.com/search/" + urllib.parse.quote(query)

    async def _run() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    await page.wait_for_selector('a[href*="/track/"]', timeout=15000)
                except Exception:
                    pass
                return await page.content()
            finally:
                await browser.close()

    try:
        html = asyncio.run(_run())
    except Exception:
        return []
    seen: List[str] = []
    for tid in re.findall(r"/track/([A-Za-z0-9]{22})", html):
        if tid not in seen:
            seen.append(tid)
        if len(seen) >= limit:
            break
    return seen


def _ddg_search_ids(query: str, limit: int = 6) -> List[str]:
    """Track ids from a DuckDuckGo html search (fast, may be rate-limited)."""
    try:
        html = _http_get(
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote("site:open.spotify.com/track " + query)
        )
    except Exception:
        return []
    if "challenge" in html.lower() and "duckduckgo" not in html.lower().split("challenge")[0][-200:]:
        return []  # CAPTCHA page
    seen: List[str] = []
    for tid in re.findall(r"open\.spotify\.com/track/([A-Za-z0-9]{22})", html):
        if tid not in seen:
            seen.append(tid)
        if len(seen) >= limit:
            break
    if seen:
        return seen
    for m in re.finditer(r"uddg=([^&\"]+)", html):
        try:
            target = urllib.parse.unquote(m.group(1))
        except Exception:
            continue
        inner = re.search(r"open\.spotify\.com/track/([A-Za-z0-9]{22})", target)
        if inner and inner.group(1) not in seen:
            seen.append(inner.group(1))
        if len(seen) >= limit:
            break
    return seen


def _track_title(track_id: str) -> Optional[str]:
    try:
        url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        data = json.loads(_http_get(url, timeout=15))
        title = str(data.get("title") or "").strip()
        return title or None
    except Exception:
        return None


def _resolve_track(query: str) -> Tuple[Optional[str], Optional[str], str]:
    """Return (track_id, title, how); track_id is None when unresolved."""
    direct = re.search(_TRACK_ID, query)
    if direct:
        tid = direct.group(1)
        return tid, _track_title(tid), "direct"

    key = query.strip().lower()
    cached = _CACHE.get(key)
    if cached and cached[2] > time.time():
        return cached[0], cached[1], "cache"

    wanted = _tokens(query)
    if not wanted:
        return None, None, "no-tokens"

    best: Tuple[float, str, Optional[str]] = (-1.0, "", None)

    # Source 1: Spotify's own search ranking (usually the exact song first).
    for tid in _spotify_search_ids(query):
        title = _track_title(tid)
        score = _match_score(wanted, title)
        if title is None:
            score = 0.9  # Spotify's top hit, but unverifiable offline
        if score > best[0]:
            best = (score, tid, title)
        if score >= 0.99:
            break

    # Source 2: web search, only if Spotify's page gave us nothing usable.
    if best[0] < 0.5:
        for tid in _ddg_search_ids(query):
            title = _track_title(tid)
            score = _match_score(wanted, title)
            if score > best[0]:
                best = (score, tid, title)
            if best[0] >= 0.99:
                break

    score, tid, title = best
    if not tid or score < 0.5:
        return None, None, "unresolved"

    _CACHE[key] = (tid, title, time.time() + _CACHE_TTL)
    return tid, title, "search"


def _open_uri(uri: str) -> None:
    if platform.system() == "Windows":
        os.startfile(uri)  # noqa: S606
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", uri], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", uri], close_fds=True)


@register("playSong")
def play_song(args: Dict[str, Any]) -> Dict[str, Any]:
    """Play a named song in the Spotify desktop app (resolves the exact track)."""
    query = args.get("query") or args.get("song") or args.get("name")
    artist = args.get("artist") or ""
    if not query:
        raise ToolError("Provide 'query' (song title) — e.g. query='Starboy'.")
    full = f"{str(query).strip()} {str(artist).strip()}".strip()

    track_id, title, how = _resolve_track(full)
    if track_id:
        try:
            _open_uri(f"spotify:track:{track_id}")
        except OSError as exc:
            raise ToolError(
                f"Spotify is not installed or does not handle spotify: URIs: {exc}"
            ) from exc
        try:
            from .media import _focus_app
            _focus_app("spotify")
        except Exception:
            pass
        return {
            "result": f"Playing '{title or full}' in the Spotify app.",
            "track_id": track_id,
            "title": title,
            "resolved_via": how,
        }

    # Fallback: hand the query to Spotify's own search screen (no auto-play).
    try:
        _open_uri("spotify:search:" + urllib.parse.quote(full))
    except OSError as exc:
        raise ToolError(f"Could not reach Spotify: {exc}") from exc
    return {
        "result": (
            f"Could not resolve an exact Spotify track for '{full}', so I opened "
            f"the search results in the Spotify app instead. Do NOT send a play "
            f"media key now — it would resume whatever was playing before."
        ),
        "track_id": None,
        "title": None,
        "resolved_via": "search-fallback",
    }


__all__ = ["play_song"]
