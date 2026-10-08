"""
Application control: launch and close applications.

Resolution order:
  1. Built-in APP_COMMANDS shortcuts (fast, cross-platform).
  2. On Windows, a cached index of everything installed on this device:
     Start menu entries (Get-StartApps) plus every .lnk shortcut on the
     Desktop and in the Start Menu (user + all-users), so any app the user
     can see on their machine can be launched by name.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from ..registry import ToolError, register
from ..backends import get_backend

APP_COMMANDS: Dict[str, Dict[str, str]] = {
    "notepad": {"exe": "notepad.exe", "image": "notepad.exe", "label": "Notepad", "linux_cmd": "gedit", "linux_image": "gedit"},
    "chrome": {"exe": "chrome.exe", "image": "chrome.exe", "label": "Google Chrome", "linux_cmd": "google-chrome-stable", "linux_image": "chrome"},
    "edge": {"exe": "msedge.exe", "image": "msedge.exe", "label": "Microsoft Edge", "linux_cmd": "microsoft-edge-stable", "linux_image": "msedge"},
    "vscode": {"exe": "code.cmd", "image": "Code.exe", "label": "Visual Studio Code", "linux_cmd": "code", "linux_image": "code"},
    "calculator": {"shell": "calc", "image": "CalculatorApp.exe", "label": "Calculator", "linux_cmd": "gnome-calculator", "linux_image": "gnome-calculator"},
    "calc": {"shell": "calc", "image": "CalculatorApp.exe", "label": "Calculator", "linux_cmd": "gnome-calculator", "linux_image": "gnome-calculator"},
    "file explorer": {"shell": "explorer", "image": "explorer.exe", "label": "File Explorer", "linux_cmd": "nautilus", "linux_image": "nautilus"},
    "explorer": {"shell": "explorer", "image": "explorer.exe", "label": "File Explorer", "linux_cmd": "nautilus", "linux_image": "nautilus"},
    "task manager": {"shell": "taskmgr", "image": "Taskmgr.exe", "label": "Task Manager", "linux_cmd": "gnome-system-monitor", "linux_image": "gnome-system-monitor"},
    "taskmanager": {"shell": "taskmgr", "image": "Taskmgr.exe", "label": "Task Manager", "linux_cmd": "gnome-system-monitor", "linux_image": "gnome-system-monitor"},
    "settings": {"uwp": "ms-settings:", "image": "SystemSettings.exe", "label": "Settings", "linux_cmd": "gnome-control-center", "linux_image": "gnome-control-center"},
    "command prompt": {"exe": "cmd.exe", "image": "cmd.exe", "label": "Command Prompt", "linux_cmd": "gnome-terminal", "linux_image": "gnome-terminal-server"},
    "cmd": {"exe": "cmd.exe", "image": "cmd.exe", "label": "Command Prompt", "linux_cmd": "gnome-terminal", "linux_image": "gnome-terminal-server"},
    "powershell": {"exe": "powershell.exe", "image": "powershell.exe", "label": "PowerShell", "linux_cmd": "pwsh", "linux_image": "pwsh"},
    "wordpad": {"shell": "write", "image": "wordpad.exe", "label": "WordPad", "linux_cmd": "abiword", "linux_image": "abiword"},
    "paint": {"shell": "mspaint", "image": "mspaint.exe", "label": "Paint", "linux_cmd": "gimp", "linux_image": "gimp"},
    "snipping tool": {"uwp": "ms-screenclip:", "image": "ScreenClippingHost.exe", "label": "Snipping Tool", "linux_cmd": "gnome-screenshot", "linux_image": "gnome-screenshot"},
}

# Loose aliases applied before the installed-app index is consulted.
ALIASES: Dict[str, str] = {
    "code": "vscode",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "google chrome": "chrome",
    "microsoft edge": "edge",
    "calc": "calculator",
    "settings app": "settings",
    "windows explorer": "file explorer",
}


# ---------------------------------------------------------------------------
# Windows installed-app discovery (Start Menu + Desktop shortcuts).
# ---------------------------------------------------------------------------

_INDEX_TTL_SECONDS = 300.0
_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: Optional[tuple[float, List[Dict[str, str]]]] = None

# PowerShell that dumps every launchable app on this machine as JSON.
_POWERSHELL_INDEX = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = @()
foreach ($a in Get-StartApps) {
    $name = [string]$a.Name
    $appid = [string]$a.AppID
    if ($name -and $appid) {
        $items += [pscustomobject]@{ name = $name; appid = $appid; lnk = ''; target = ''; priority = 1 }
    }
}
try { $sh = New-Object -ComObject WScript.Shell } catch { $sh = $null }
$dirs = @(
    "$env:USERPROFILE\Desktop",
    "$env:PUBLIC\Desktop",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs"
)
$seen = @{}
foreach ($d in $dirs) {
    if (-not (Test-Path -LiteralPath $d)) { continue }
    $priority = if ($d -like '*\Desktop*') { 3 } else { 2 }
    Get-ChildItem -LiteralPath $d -Recurse -Filter *.lnk -File -ErrorAction SilentlyContinue | ForEach-Object {
        $path = $_.FullName
        if ($seen.ContainsKey($path)) { return }
        $seen[$path] = $true
        $target = ''
        if ($sh) { try { $target = [string]$sh.CreateShortcut($path).TargetPath } catch { $target = '' } }
        $items += [pscustomobject]@{
            name     = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
            appid    = ''
            lnk      = $path
            target   = $target
            priority = $priority
        }
    }
}
ConvertTo-Json -InputObject @($items) -Compress -Depth 4
"""

# Well-known Windows folder GUIDs used in Start-menu AppIDs ("{GUID}\app.exe").
_KNOWN_FOLDERS: Dict[str, Any] = {
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": lambda: os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32"),
    "{6D809377-6AF0-444B-8957-A3773F02200E}": lambda: os.environ.get("ProgramFiles", r"C:\Program Files"),
    "{7C5A40EF-1028-45EA-A562-A82B0A5B64BC}": lambda: os.environ.get("ProgramW6432", r"C:\Program Files"),
    "{D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27}": lambda: os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
}


def _build_windows_index() -> List[Dict[str, str]]:
    """Collect Start-menu apps + Desktop/Start-menu shortcuts (cached)."""
    global _INDEX_CACHE
    with _INDEX_LOCK:
        if _INDEX_CACHE and (time.time() - _INDEX_CACHE[0]) < _INDEX_TTL_SECONDS:
            return _INDEX_CACHE[1]

        entries: List[Dict[str, str]] = []
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_INDEX],
                capture_output=True, text=True, timeout=45,
            )
            raw = json.loads(proc.stdout.strip() or "[]")
            if isinstance(raw, dict):
                raw = [raw]
            for row in raw:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                entries.append({
                    "name": name,
                    "appid": str(row.get("appid") or "").strip(),
                    "lnk": str(row.get("lnk") or "").strip(),
                    "target": str(row.get("target") or "").strip(),
                    "priority": str(row.get("priority") or "1"),
                })
        except Exception:
            entries = []

        _INDEX_CACHE = (time.time(), entries)
        return entries


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _match_score(query: str, entry: Dict[str, str]) -> int:
    """0 = no match; higher = better (exact > prefix > contains > tokens)."""
    name = _norm(entry.get("name", ""))
    if not name:
        return 0
    if query == name:
        return 100
    if name.startswith(query):
        return 80
    if query in name:
        return 60
    query_tokens, name_tokens = set(query.split()), set(name.split())
    if query_tokens and query_tokens <= name_tokens:
        return 55
    if len(query) >= 3 and any(t.startswith(query) for t in name_tokens):
        return 50
    return 0


def _resolve_known_folder_path(appid: str) -> Optional[str]:
    """Turn shell-namespace paths like `{1AC14E77-...}\\charmap.exe` into a path."""
    m = re.match(r"^(\{[0-9A-Fa-f-]+\})\\(.+)$", appid)
    if not m:
        return None
    factory = _KNOWN_FOLDERS.get(m.group(1).upper())
    if not factory:
        return None
    root = factory()
    if not root:
        return None
    candidate = os.path.join(root, m.group(2))
    return candidate if os.path.exists(candidate) else None


def _entry_to_spec(entry: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Convert a discovery index entry into a launch spec."""
    label = entry.get("name") or "application"
    lnk = entry.get("lnk") or ""
    if lnk and os.path.exists(lnk):
        spec: Dict[str, str] = {"lnk": lnk, "label": label}
        target = entry.get("target") or ""
        if target:
            spec["image"] = os.path.basename(target)
        return spec

    appid = (entry.get("appid") or "").strip()
    if not appid:
        return None
    if appid.lower().startswith(("http://", "https://")):
        return None
    if os.path.isabs(appid):
        return {"exe": appid, "label": label, "image": os.path.basename(appid)}
    resolved = _resolve_known_folder_path(appid)
    if resolved:
        return {"exe": resolved, "label": label, "image": os.path.basename(resolved)}
    return {"appid": appid, "label": label}


def _discover_app(key: str) -> Optional[Dict[str, str]]:
    """Best match for `key` among the apps installed on this Windows device."""
    if platform.system() != "Windows":
        return None
    entries = _build_windows_index()
    if not entries:
        return None
    query = _norm(key)
    best: Optional[Dict[str, str]] = None
    best_key = (0, 0)
    for entry in entries:
        score = _match_score(query, entry)
        if score <= 0:
            continue
        try:
            priority = int(entry.get("priority") or 0)
        except ValueError:
            priority = 0
        ranked = (score, priority)
        if ranked > best_key:
            best_key, best = ranked, entry
    if best is None:
        return None
    return _entry_to_spec(best)


def _resolve_app(key: str) -> Dict[str, str]:
    norm = _norm(key)
    if norm in APP_COMMANDS:
        return APP_COMMANDS[norm]
    if norm in ALIASES and ALIASES[norm] in APP_COMMANDS:
        return APP_COMMANDS[ALIASES[norm]]

    discovered = _discover_app(key)
    if discovered:
        return discovered

    supported = ", ".join(sorted({v["label"] for v in APP_COMMANDS.values()}))
    raise ToolError(
        f"No app named '{key}' was found on this device (checked Start Menu and "
        f"Desktop shortcuts). Built-in shortcuts: {supported}. Otherwise give "
        f"the exact app name as it appears in the Start Menu."
    )


def _is_hyprland() -> bool:
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "hyprland"


def _launch_hyprland(cmd: str, floating: bool, size: str = "60% 60%") -> None:
    prefix = f"[float size {size} center]" if floating else ""
    subprocess.Popen(
        f"hyprctl dispatch exec -- {prefix} {cmd}",
        shell=True,
        close_fds=True,
        start_new_session=True,
    )


def _close_uwp(appid: str) -> List[str]:
    """Stop a packaged (UWP/Store) app by AUMID. Returns process names killed."""
    family = appid.split("!", 1)[0]
    script = (
        "$fam = '" + family.replace("'", "''") + "'; "
        "$pkg = Get-AppxPackage | Where-Object { $_.PackageFamilyName -eq $fam } | Select-Object -First 1; "
        "if ($pkg -and $pkg.InstallLocation) { "
        "  Get-Process | Where-Object { $_.Path -and $_.Path -like ($pkg.InstallLocation + '\\*') } | "
        "  ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; $_.ProcessName } "
        "}"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    except Exception:
        return []


@register("openApplication")
def open_application(args: Dict[str, Any]) -> Dict[str, Any]:
    name = args.get("name") or args.get("application")
    if not name:
        raise ToolError("Parameter 'name' (application name) is required.")
    spec = _resolve_app(str(name))
    floating = bool(args.get("floating", False))
    size = args.get("size", "60% 60%")
    linux_cmd = spec.get("linux_cmd")
    if floating and _is_hyprland() and linux_cmd:
        _launch_hyprland(linux_cmd, floating=True, size=size)
    else:
        get_backend().launcher.launch(spec)
    return {"result": f"{spec.get('label', name)} opened."}


@register("closeApplication")
def close_application(args: Dict[str, Any]) -> Dict[str, Any]:
    name = args.get("name") or args.get("application")
    force = bool(args.get("force", False))
    if not name:
        raise ToolError("Parameter 'name' (application name) is required.")
    spec = _resolve_app(str(name))

    image = spec.get("image")
    if image:
        get_backend().launcher.close(spec, force)
        return {"result": f"Closed {spec.get('label', name)}."}

    if spec.get("appid") and "!" in spec["appid"]:
        killed = _close_uwp(spec["appid"])
        if killed:
            return {"result": f"Closed {spec.get('label', name)} ({', '.join(killed)})."}
        raise ToolError(
            f"{spec.get('label', name)} is not running (or its process could not be identified)."
        )

    raise ToolError(
        f"Could not determine the process name for '{name}'. "
        f"Try closeWindow with the window title instead."
    )


@register("openUri")
def open_uri(args: Dict[str, Any]) -> Dict[str, Any]:
    """Open a protocol URI (spotify:track:..., spotify:search:..., steam://...).

    Windows routes these to the registered desktop handler, so
    `spotify:track:<id>` starts the song in the Spotify app and
    `spotify:search:<query>` opens the search results there.
    """
    uri = str(args.get("uri") or args.get("url") or "").strip()
    if not uri:
        raise ToolError("Parameter 'uri' is required (e.g. 'spotify:search:shape of you').")
    if ":" not in uri:
        raise ToolError(
            f"'{uri}' is not a URI. Use openWebsite for web pages and "
            f"openApplication for apps."
        )
    try:
        if platform.system() == "Windows":
            os.startfile(uri)  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", uri], close_fds=True)
        else:
            subprocess.Popen(["xdg-open", uri], close_fds=True)
    except OSError as exc:
        raise ToolError(f"No app on this device handles '{uri}': {exc}") from exc
    return {"result": f"Opened {uri}."}


__all__ = ["open_application", "close_application", "open_uri", "APP_COMMANDS"]
