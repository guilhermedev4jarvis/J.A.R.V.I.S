"""
Action: network_status — local/public IP, connectivity, and basic interface info.

No browser, no privileges beyond what the OS already exposes to a normal user.
"""
from __future__ import annotations

import json
import platform
import socket
import urllib.error
import urllib.request
from typing import Optional

from core import outcome

_TIMEOUT = 4.0
_PUBLIC_IP_URLS = (
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)


def _log(msg: str, player=None) -> None:
    print(f"[Network] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _local_ip() -> str:
    """Best-effort primary LAN address without sending traffic."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packet is sent; the OS just picks the route to this address.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown"


def _hostname() -> str:
    try:
        return socket.gethostname() or "unknown"
    except Exception:
        return "unknown"


def _public_ip() -> Optional[str]:
    for url in _PUBLIC_IP_URLS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MARK-LVI-network_status/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
            if not body:
                continue
            if body.startswith("{"):
                data = json.loads(body)
                ip = (data.get("ip") or "").strip()
                if ip:
                    return ip
            # plain-text body
            candidate = body.split()[0]
            if candidate.count(".") == 3 or ":" in candidate:
                return candidate
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            continue
        except Exception:
            continue
    return None


def _can_reach(host: str = "1.1.1.1", port: int = 443) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT):
            return True
    except OSError:
        return False


def network_status(parameters: dict, player=None, session_memory=None) -> str:
    """Report connectivity and addresses. parameters may include detail=full."""
    params = parameters or {}
    detail = str(params.get("detail") or "summary").strip().lower()

    host = _hostname()
    local = _local_ip()
    online = _can_reach()
    public = _public_ip() if online else None

    facts = {
        "hostname": host,
        "local_ip": local,
        "online": online,
        "os": platform.system(),
    }
    if public:
        facts["public_ip"] = public
    elif online:
        facts["public_ip"] = "unavailable"
    else:
        facts["public_ip"] = "offline"

    if detail in ("full", "verbose", "detailed"):
        facts["detail"] = (
            f"hostname={host}; lan={local}; wan={facts['public_ip']}; "
            f"internet={'yes' if online else 'no'}"
        )

    msg = (
        f"Host {host}, LAN {local}, "
        + (f"public IP {public}, " if public else "public IP unavailable, ")
        + ("internet reachable." if online else "no internet connectivity.")
    )
    _log(msg, player)
    return outcome.done("network_status", **facts)


_LEGACY_TOOL = {
    "name": "network_status",
    "description": (
        "Reports network connectivity: hostname, local (LAN) IP address, "
        "public (WAN) IP when reachable, and whether the internet is up. "
        "Use when the user asks about IP address, connection status, "
        "whether they are online, or network info."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "detail": {
                "type": "STRING",
                "description": "summary (default) or full for a denser fact line.",
            },
        },
        "required": [],
    },
    "handler": network_status,
}
