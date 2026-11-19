
"""Action publica: honeypot TCP local defensivo."""
from __future__ import annotations

from core.outcome import failed
from ._honeypot_rede_local_impl import run as _run


def honeypot_rede_local(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("honeypot_rede_local", str(e)[:240])


TOOL = {
    "name": "honeypot_rede_local",
    "description": (
        "Honeypot TCP local (isca) em thread daemon para registrar scans na LAN. "
        "USE para isca/honeypot/armadilha de rede. NAO USE como firewall ou VPN. "
        "action=iniciar|parar|status|historico; port=1024..65535."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "mode": {"type": "STRING"},
            "port": {"type": "INTEGER"},
            "banner": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": honeypot_rede_local,
    "tier": "core",
    "risk": "review",
}
