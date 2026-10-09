"""
WhatsApp Web automation via Playwright.

Send a WhatsApp message to ANY contact by NAME (no phone number needed):

    sendWhatsAppMessage({ "contact": "Vivek", "message": "Hi Vivek, where are you?" })

This drives the same automation browser used by the desktopBrowser* tools, so
the WhatsApp Web login (QR scan) is remembered in the persistent profile
(~/.kora_browser_data in managed mode, or the user's own Chrome in CDP mode).
The user only has to scan the QR code once; after that any contact can be
messaged by name.

Domains and DOM structure on web.whatsapp.com change fairly often, so every
step below tries a list of selectors (with graceful fallbacks) instead of a
single brittle one.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..registry import STATE, ToolError, register
from .browser import _page, _run

log = logging.getLogger("kora.tools.whatsapp")

WHATSAPP_URL = "https://web.whatsapp.com"

# --- Selectors (ordered fallbacks) ------------------------------------------

# Present once WhatsApp Web has finished loading and the user is logged in.
_LOGIN_READY_SELECTORS = [
    "#pane-side",
    '[data-testid="chat-list"]',
    'div[aria-label="Chat list"]',
]

# Present only when the user still needs to link a device (not logged in).
_QR_SELECTORS = [
    'canvas[aria-label*="Scan"]',
    'div[data-testid="qrcode"]',
    '[aria-label*="Scan this QR code"]',
    '[aria-label*="link a device"]',
]

# The chat/contact search input.
_SEARCH_SELECTORS = [
    '#side div[contenteditable="true"][data-tab="3"]',
    '[data-testid="chat-list-search"]',
    '#side input[type="text"]',
    'input[aria-label*="Search"]',
    'div[contenteditable="true"][aria-label*="Search"]',
    '[aria-label="Search input textbox"]',
    '[title="Search input textbox"]',
    '#side div[contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"]',
]

# A single search result / conversation row.
_RESULT_ITEM_SELECTORS = [
    '#pane-side [role="listitem"]',
    '[data-testid="chat-list"] [role="listitem"]',
    'div[aria-label="Chat list"] [role="listitem"]',
    '#pane-side [data-testid="cell-frame-container"]',
    '#pane-side [data-testid^="list-item-"]',
]

# The message compose box inside an open conversation.
_COMPOSE_SELECTORS = [
    'footer div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"][data-tab="6"]',
    '[data-testid="conversation-compose-box-input"]',
    'footer div[contenteditable="true"]',
    '[aria-label="Type a message"]',
    '[title="Type a message"]',
]

# The conversation header (shows the currently open contact/group name).
_HEADER_SELECTORS = [
    '#main header span[title]',
    '#main header [data-testid="conversation-info-header-chat-title"]',
    '#main header span[dir="auto"]',
    'header span[title]',
]


def _norm(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


async def _find_now(page: Any, selectors: List[str]) -> Optional[Any]:
    """Return the first matching locator right now, or None (no waiting)."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


async def _get_whatsapp_page() -> Any:
    """Reuse an existing web.whatsapp.com tab, else open a dedicated one."""
    page = await _page()
    try:
        if "web.whatsapp.com" in (page.url or ""):
            return page
    except Exception:
        pass

    ctx = getattr(STATE, "context", None)
    if ctx is not None:
        for existing in list(ctx.pages):
            try:
                if "web.whatsapp.com" in (existing.url or ""):
                    STATE.page = existing
                    return existing
            except Exception:
                continue
        try:
            new_page = await ctx.new_page()
            await new_page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30000)
            STATE.page = new_page
            return new_page
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not open a dedicated WhatsApp tab: %s", exc)

    await page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30000)
    return page


async def _wait_logged_in(page: Any, timeout_s: float = 20.0) -> bool:
    """Wait for the chat list. Returns False if the QR 'link device' screen shows."""
    for _ in range(max(1, int(timeout_s / 0.5))):
        if await _find_now(page, _LOGIN_READY_SELECTORS) is not None:
            return True
        if await _find_now(page, _QR_SELECTORS) is not None:
            return False
        await asyncio.sleep(0.5)
    return await _find_now(page, _LOGIN_READY_SELECTORS) is not None


async def _read_item_name(item: Any) -> Optional[str]:
    """Best-effort read of the contact/group name from a result row."""
    for sel in ('span[title]', '[data-testid="cell-frame-title"]', 'span[dir="auto"]'):
        try:
            el = item.locator(sel).first
            if await el.count() > 0:
                title = await el.get_attribute("title")
                if title:
                    return title
                text = (await el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return None


def _looks_like(target: str, name: Optional[str]) -> bool:
    t, n = _norm(target), _norm(name)
    if not n:
        return False
    if t == n or n.startswith(t) or t in n or n in t:
        return True
    return t.split()[0] == n.split()[0]


async def _open_chat(page: Any, contact: str) -> Tuple[Optional[str], List[str], bool]:
    """Search for `contact` and open the best-matching chat.

    Returns (matched_name, candidate_names, confident). `confident` is True only
    when we explicitly clicked a result whose name clearly matched `contact`.
    """
    search = await _find_now(page, _SEARCH_SELECTORS)
    if search is None:
        raise ToolError(
            "Could not find WhatsApp's search box. Make sure WhatsApp Web is "
            "open and logged in, then ask me again."
        )

    try:
        await search.click(timeout=5000)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Could not focus WhatsApp's search box: {exc}")

    await asyncio.sleep(0.3)
    try:
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    await page.keyboard.type(contact, delay=40)
    await asyncio.sleep(1.5)  # let the result list render

    items = None
    for sel in _RESULT_ITEM_SELECTORS:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                items = loc
                break
        except Exception:
            continue

    candidates: List[str] = []
    if items is not None:
        for i in range(min(await items.count(), 20)):
            name = await _read_item_name(items.nth(i))
            if name:
                candidates.append(name)

    # Score candidates against the requested name.
    target = _norm(contact)
    best_idx: Optional[int] = None
    best_score = -1
    for i, name in enumerate(candidates):
        n = _norm(name)
        if n == target:
            score = 100
        elif n.startswith(target) or target.startswith(n):
            score = 80
        elif target in n:
            score = 60
        elif n in target and len(n) >= 3:
            score = 40
        else:
            score = 20 * len(set(target.split()) & set(n.split())) or -1
        if score > best_score:
            best_score, best_idx = score, i

    # If we have a reasonable match, click it directly.
    if items is not None and best_idx is not None and best_score >= 40:
        matched_name = candidates[best_idx]
        for click_target in (
            items.nth(best_idx),
            items.nth(best_idx).locator("span[title]").first,
        ):
            try:
                await click_target.click(timeout=5000)
                return matched_name, candidates, True
            except Exception:
                continue
        # Fall through to the Enter shortcut below if clicking failed.

    # Otherwise open the top-ranked result (WhatsApp ranks the best match first).
    # We are NOT confident here; the caller must verify via the chat header.
    try:
        await page.keyboard.press("Enter")
    except Exception:
        pass
    return (candidates[0] if candidates else None), candidates, False


async def _header_name(page: Any) -> Optional[str]:
    for sel in _HEADER_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                title = await loc.get_attribute("title")
                if title:
                    return title
                text = (await loc.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return None


async def _wait_for_compose(page: Any, timeout_s: float = 10.0) -> Optional[Any]:
    for _ in range(max(1, int(timeout_s / 0.5))):
        compose = await _find_now(page, _COMPOSE_SELECTORS)
        if compose is not None:
            return compose
        await asyncio.sleep(0.5)
    return None


async def _send_async(args: Dict[str, Any]) -> Dict[str, Any]:
    contact = str(args.get("contact") or args.get("to") or "").strip()
    message = str(args.get("message") or args.get("text") or "")
    if not contact:
        raise ToolError("Parameter 'contact' (the WhatsApp contact's name) is required.")
    if not message.strip():
        raise ToolError("Parameter 'message' (the text to send) is required.")

    page = await _get_whatsapp_page()

    if not await _wait_logged_in(page):
        try:
            await page.bring_to_front()
        except Exception:
            pass
        raise ToolError(
            "WhatsApp Web is not logged in. I've opened it and it's showing a QR "
            "code. Please scan it once from your phone (WhatsApp > Linked devices "
            "> Link a device). After that I can message any contact by name."
        )

    matched, candidates, confident = await _open_chat(page, contact)

    compose = await _wait_for_compose(page)
    if compose is None:
        found = ", ".join(candidates[:6]) if candidates else "none"
        raise ToolError(
            f"Couldn't find or open a WhatsApp chat for '{contact}'. "
            f"Contacts I saw: {found}. Try the exact name as saved in WhatsApp."
        )

    # Guard against messaging the wrong person. If we did not confidently click
    # a matching search result, we REQUIRE the open chat's header to match.
    header = await _header_name(page)
    header_ok = bool(header) and _looks_like(contact, header)
    if not confident and not header_ok:
        found = ", ".join(candidates[:6]) if candidates else "none"
        shown = header or "an unknown chat"
        raise ToolError(
            f"I couldn't confirm a WhatsApp chat for '{contact}' (saw '{shown}'), "
            f"so I did NOT send anything. Names I found: {found}. "
            f"Tell me the exact name as saved in WhatsApp."
        )
    if confident and header and not header_ok:
        found = ", ".join(candidates[:6]) if candidates else "none"
        raise ToolError(
            f"I opened a chat called '{header}', which doesn't look like "
            f"'{contact}', so I did NOT send anything. Names I found: {found}."
        )

    # Type and send. In WhatsApp Web the Enter key sends by default.
    await compose.click(timeout=5000)
    await asyncio.sleep(0.2)
    for i, line in enumerate(message.split("\n")):
        if i:
            await page.keyboard.press("Shift+Enter")
        if line:
            await page.keyboard.type(line, delay=12)
    await asyncio.sleep(0.3)
    await page.keyboard.press("Enter")
    await asyncio.sleep(1.2)

    who = header or matched or contact
    return {
        "result": f"Sent a WhatsApp message to {who}: \"{message.strip()}\"",
        "contact": who,
        "message": message.strip(),
    }


@register("sendWhatsAppMessage")
def send_whatsapp_message(args: Dict[str, Any]) -> Dict[str, Any]:
    """Send a WhatsApp message to a contact by name via WhatsApp Web."""
    return _run(_send_async(args))
