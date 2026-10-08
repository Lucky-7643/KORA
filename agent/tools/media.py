"""
System media control via the global Windows/Linux media keys.

These are hardware-level keys (play/pause, next, previous, volume), so they
control whatever app currently owns the media session — the Spotify desktop
app, VLC, YouTube in a browser, etc. Pass `app` to focus a specific player
first so the keypress is guaranteed to land on it.
"""

from __future__ import annotations

import platform
import time
from typing import Any, Dict, Optional

from ..registry import ToolError, register

# Virtual-key codes (Windows) for the media/volume keys.
_MEDIA_KEYS: Dict[str, int] = {
    "play_pause": 0xB3,
    "play": 0xB3,
    "pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}

_ALIASES: Dict[str, str] = {
    "toggle": "play_pause",
    "resume": "play_pause",
    "skip": "next",
    "forward": "next",
    "back": "previous",
    "prev": "previous",
    "vol_up": "volume_up",
    "vol_down": "volume_down",
    "volup": "volume_up",
    "voldown": "volume_down",
}

ACTIONS = sorted(set(_MEDIA_KEYS) | set(_ALIASES))


def _focus_app(app: str) -> bool:
    """Bring a running application's window to the foreground (Windows)."""
    if platform.system() != "Windows":
        return False
    try:
        import psutil
        import win32gui
        import win32process

        target = str(app).strip().lower()
        if not target.endswith(".exe"):
            target += ".exe"
        pids = {
            p.pid
            for p in psutil.process_iter(["name"])
            if (p.info.get("name") or "").lower() == target
        }
        if not pids:
            return False

        handles: list[int] = []

        def _cb(hwnd: int, _extra: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return
            if pid in pids:
                handles.append(hwnd)

        win32gui.EnumWindows(_cb, None)
        if not handles:
            return False
        hwnd = handles[0]
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass
        try:
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _send_media_key(vk: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


@register("mediaControl")
def media_control(args: Dict[str, Any]) -> Dict[str, Any]:
    """Play/pause/skip/volume for the current media session (Spotify etc.)."""
    raw = str(args.get("action") or "play_pause").strip().lower()
    action = _ALIASES.get(raw, raw.replace("-", "_").replace(" ", "_"))
    if action not in _MEDIA_KEYS:
        raise ToolError(
            f"Unknown media action '{args.get('action')}'. "
            f"Valid: {', '.join(ACTIONS)}."
        )
    if platform.system() == "Windows":
        import ctypes
        if not ctypes.windll.user32:
            raise ToolError("Media keys are unavailable on this system.")

    app = args.get("app") or args.get("name")
    focused = False
    if app:
        focused = _focus_app(str(app))
        if focused:
            time.sleep(0.3)

    _send_media_key(_MEDIA_KEYS[action])

    msg = f"Sent media key '{action}'."
    if app:
        msg += f" Focused '{app}' first." if focused else f" ('{app}' is not running; sent to the active media session.)"
    return {"result": msg, "action": action, "focused_app": focused}


__all__ = ["media_control", "ACTIONS"]
