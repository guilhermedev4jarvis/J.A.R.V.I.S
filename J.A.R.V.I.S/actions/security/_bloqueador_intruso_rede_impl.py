"""Contencao defensiva de dispositivos desconhecidos na rede local."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from core.outcome import done, failed

_BASE = Path(__file__).resolve().parents[2]
_GUARD_CFG = _BASE / "config" / "network_guard.json"
_QUARANTINE_STATE = _BASE / "memory" / "quarantined_devices.json"


def _load_whitelist() -> set[str]:
    if _GUARD_CFG.exists():
        try:
            data = json.loads(_GUARD_CFG.read_text(encoding="utf-8"))
            items = data.get("whitelist") or data.get("trusted_macs") or []
            return {str(x).strip().lower() for x in items}
        except Exception:
            pass
    return set()


def _scan_devices() -> List[Dict[str, Any]]:
    try:
        from actions.system import _radar_dispositivos_wifi_impl as radar
        if hasattr(radar, "scan_network"):
            res = radar.scan_network()
            if isinstance(res, list):
                return res
            if isinstance(res, dict):
                return res.get("devices", [])
    except Exception:
        pass
    return []


def _record_quarantine(mac: str, ip: str, blocked: bool) -> None:
    _QUARANTINE_STATE.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if _QUARANTINE_STATE.exists():
        try:
            current = json.loads(_QUARANTINE_STATE.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    key = mac or ip
    if blocked:
        current[key] = {"mac": mac, "ip": ip, "quarantined": True}
    else:
        current.pop(key, None)
    _QUARANTINE_STATE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "scan").lower()
    target_mac = str(params.get("target_mac") or "").strip().lower()
    target_ip = str(params.get("target_ip") or "").strip()
    confirmed = bool(params.get("confirmed", False))

    whitelist = _load_whitelist()

    if action == "scan":
        devices = _scan_devices()
        unknown = [d for d in devices if str(d.get("mac", "")).lower() not in whitelist]
        return done(
            "bloqueador_intruso_rede",
            f"Varredura concluida: {len(unknown)} dispositivo(s) fora da whitelist.",
            {"total_devices": len(devices), "unknown_devices": unknown, "whitelist_count": len(whitelist)},
        )

    if action == "quarantine":
        if not (target_mac or target_ip):
            return failed("bloqueador_intruso_rede", "Informe target_mac ou target_ip para isolar o dispositivo.")
        if target_mac and target_mac in whitelist:
            return failed("bloqueador_intruso_rede", f"Dispositivo {target_mac} esta na whitelist e nao pode ser bloqueado.")
        if not confirmed:
            return failed(
                "bloqueador_intruso_rede",
                f"Confirmacao explicita necessaria (confirmed=True) para isolar {target_mac or target_ip}.",
            )
        if target_ip:
            rule_name = f"JARVIS_BLOCK_{target_ip.replace('.', '_')}"
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule_name}", "dir=in", "action=block", f"remoteip={target_ip}"],
                capture_output=True,
                text=True,
                check=False,
            )
        _record_quarantine(target_mac, target_ip, True)
        try:
            from core import audit
            audit.log_event("network_intruder_quarantined", {"mac": target_mac, "ip": target_ip})
        except Exception:
            pass
        return done("bloqueador_intruso_rede", f"Dispositivo {target_mac or target_ip} isolado.", {"mac": target_mac, "ip": target_ip})

    if action == "release":
        if target_ip:
            rule_name = f"JARVIS_BLOCK_{target_ip.replace('.', '_')}"
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True,
                text=True,
                check=False,
            )
        _record_quarantine(target_mac, target_ip, False)
        return done("bloqueador_intruso_rede", f"Isolamento removido para {target_mac or target_ip}.", {"mac": target_mac, "ip": target_ip})

    q_data = json.loads(_QUARANTINE_STATE.read_text(encoding="utf-8")) if _QUARANTINE_STATE.exists() else {}
    return done("bloqueador_intruso_rede", "Status da quarentena de rede.", {"quarantined": q_data, "whitelist_size": len(whitelist)})