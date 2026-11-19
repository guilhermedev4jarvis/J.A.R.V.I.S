"""
window_manager — list, focus, minimise, restore, and arrange windows.

Complements open_app. Uses platform-native mechanisms; reports honestly when
the platform cannot drive windows (Wayland without portals, missing perms).
"""
from __future__ import annotations

import platform
import subprocess
from typing import Optional

from core.outcome import done, failed, unverified
from core import platform_support

_OS = platform.system()
_support = platform_support.detect()


def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        kw = {}
        if _OS == "Windows":
            kw["creationflags"] = 0x08000000
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, **kw
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 1, "", str(e)


def _list_windows_windows() -> list[dict]:
    """Enumerate visible top-level windows on Windows via PowerShell."""
    ps = r"""
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc lp, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
}
"@
$out = @()
[W]::EnumWindows({
  param($h, $l)
  if (-not [W]::IsWindowVisible($h)) { return $true }
  $sb = New-Object System.Text.StringBuilder 512
  [void][W]::GetWindowText($h, $sb, $sb.Capacity)
  $title = $sb.ToString()
  if ([string]::IsNullOrWhiteSpace($title)) { return $true }
  $pid = [uint32]0
  [void][W]::GetWindowThreadProcessId($h, [ref]$pid)
  $out += [PSCustomObject]@{ Handle = [int64]$h; Title = $title; Pid = $pid }
  return $true
}, [IntPtr]::Zero)
$out | ConvertTo-Json -Compress
"""
    code, out, err = _run(
        ["powershell", "-NoProfile", "-Command", ps], timeout=12
    )
    if code != 0 or not out:
        return []
    import json
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [
            {"handle": str(w.get("Handle", "")), "title": w.get("Title", ""), "pid": w.get("Pid")}
            for w in data
            if w.get("Title")
        ]
    except Exception:
        return []


def _list_windows_macos() -> list[dict]:
    script = '''
    tell application "System Events"
      set wins to {}
      repeat with p in (every process whose background only is false)
        try
          set pname to name of p
          repeat with w in (every window of p)
            try
              set end of wins to (pname & " — " & (name of w as text))
            end try
          end repeat
        end try
      end repeat
      set AppleScript's text item delimiters to linefeed
      return wins as text
    end tell
    '''
    code, out, err = _run(["osascript", "-e", script])
    if code != 0:
        return []
    return [{"title": line, "handle": "", "pid": None} for line in out.splitlines() if line.strip()]


def _list_windows_linux() -> list[dict]:
    # Prefer wmctrl, then xdotool
    code, out, err = _run(["wmctrl", "-l"])
    if code == 0 and out:
        rows = []
        for line in out.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 4:
                rows.append({"handle": parts[0], "title": parts[3], "pid": None})
        return rows
    code, out, err = _run(["xdotool", "search", "--name", ".*"])
    if code != 0 or not out:
        return []
    rows = []
    for hid in out.splitlines()[:40]:
        hid = hid.strip()
        if not hid:
            continue
        c2, title, _ = _run(["xdotool", "getwindowname", hid])
        if c2 == 0 and title:
            rows.append({"handle": hid, "title": title, "pid": None})
    return rows


def list_windows() -> list[dict]:
    if _OS == "Windows":
        return _list_windows_windows()
    if _OS == "Darwin":
        return _list_windows_macos()
    return _list_windows_linux()


def _match(windows: list[dict], query: str) -> Optional[dict]:
    q = query.strip().lower()
    if not q:
        return None
    # Exact then substring
    for w in windows:
        if w["title"].lower() == q:
            return w
    for w in windows:
        if q in w["title"].lower():
            return w
    return None


def _focus(win: dict) -> tuple[bool, str]:
    if not _support.can_focus_windows:
        return False, "this platform does not allow focusing windows from other apps"
    if _OS == "Windows":
        handle = win.get("handle") or ""
        if not handle:
            return False, "no window handle"
        ps = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class F {{
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}}
"@
$h = [IntPtr]{handle}
[F]::ShowWindow($h, 9) | Out-Null
[F]::SetForegroundWindow($h) | Out-Null
"""
        code, _, err = _run(["powershell", "-NoProfile", "-Command", ps])
        return (code == 0, err or "ok")
    if _OS == "Darwin":
        title = win.get("title", "")
        # title format "App — Window"
        app = title.split(" — ")[0] if " — " in title else title
        script = f'tell application "{app}" to activate'
        code, _, err = _run(["osascript", "-e", script])
        return (code == 0, err or "ok")
    # Linux
    handle = win.get("handle") or ""
    if handle:
        code, _, err = _run(["wmctrl", "-ia", handle])
        if code == 0:
            return True, "ok"
        code, _, err = _run(["xdotool", "windowactivate", handle])
        return (code == 0, err or "ok")
    return False, "no window handle"


def _minimise(win: dict) -> tuple[bool, str]:
    if _OS == "Windows":
        handle = win.get("handle") or ""
        if not handle:
            return False, "no window handle"
        ps = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M {{
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}}
"@
[M]::ShowWindow([IntPtr]{handle}, 6) | Out-Null
"""
        code, _, err = _run(["powershell", "-NoProfile", "-Command", ps])
        return (code == 0, err or "ok")
    if _OS == "Darwin":
        title = win.get("title", "")
        app = title.split(" — ")[0] if " — " in title else title
        script = f'''
        tell application "System Events"
          tell process "{app}"
            try
              set value of attribute "AXMinimized" of window 1 to true
            end try
          end tell
        end tell
        '''
        code, _, err = _run(["osascript", "-e", script])
        return (code == 0, err or "ok")
    handle = win.get("handle") or ""
    if handle:
        code, _, err = _run(["xdotool", "windowminimize", handle])
        return (code == 0, err or "ok")
    return False, "minimise not available"


def window_manager(parameters=None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").strip().lower()
    query = (params.get("title") or params.get("name") or "").strip()

    if action in ("list", "show", "enumerate"):
        wins = list_windows()
        if not wins:
            reason = "no windows found"
            if _OS == "Linux" and not _support.can_focus_windows:
                reason = "no windows found (Wayland often blocks window listing)"
            return failed("window_manager", reason, action="list")
        # Cap output for the model
        lines = [f"{i+1}. {w['title']}" for i, w in enumerate(wins[:25])]
        return done(
            "window_manager",
            action="list",
            count=len(wins),
            windows=" | ".join(lines),
        )

    if not query:
        return failed("window_manager", "title/name is required for this action")

    wins = list_windows()
    target = _match(wins, query)
    if not target:
        sample = "; ".join(w["title"] for w in wins[:8]) or "(none)"
        return failed(
            "window_manager",
            f"no window matching '{query}'",
            available=sample,
        )

    if action in ("focus", "activate", "raise", "bring_to_front"):
        ok, detail = _focus(target)
        if ok:
            return done("window_manager", action="focus", title=target["title"])
        return failed("window_manager", detail or "focus failed", title=target["title"])

    if action in ("minimise", "minimize", "min"):
        ok, detail = _minimise(target)
        if ok:
            return done("window_manager", action="minimise", title=target["title"])
        return unverified("window_manager", detail or "minimise may not be confirmed", title=target["title"])

    if action in ("close",):
        # Prefer OS close rather than killing the process
        if _OS == "Windows" and target.get("handle"):
            ps = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class C {{
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}}
"@
[C]::PostMessage([IntPtr]{target['handle']}, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
"""
            code, _, err = _run(["powershell", "-NoProfile", "-Command", ps])
            if code == 0:
                return started("window_manager", action="close", title=target["title"])
            return failed("window_manager", err or "close failed", title=target["title"])
        if _OS == "Linux" and target.get("handle"):
            code, _, err = _run(["wmctrl", "-ic", target["handle"]])
            if code == 0:
                return started("window_manager", action="close", title=target["title"])
            return failed("window_manager", err or "close failed")
        return failed("window_manager", "close not implemented for this platform via window_manager; use computer_control close_app")

    return failed(
        "window_manager",
        f"unknown action '{action}'",
        allowed="list, focus, minimise, close",
    )


_LEGACY_TOOL = {
    "name": "window_manager",
    "description": (
        "Lists open windows and can focus, minimise or close one by title. "
        "Use when the user asks which windows are open, to bring an app to the "
        "front, minimise it, or close a specific window by name. "
        "Actions: list, focus, minimise, close. "
        "Prefer open_app to launch software; use this to manage windows that "
        "are already open."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | focus | minimise | close",
            },
            "title": {
                "type": "STRING",
                "description": "Full or partial window title (required except for list).",
            },
            "name": {
                "type": "STRING",
                "description": "Alias for title.",
            },
        },
        "required": ["action"],
    },
    "handler": window_manager,
    "tier": "core",
}
