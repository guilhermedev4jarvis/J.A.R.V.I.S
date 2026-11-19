"""Background workers started at boot (daemon threads, non-fatal failures)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

_log = logging.getLogger("jarvis.background")


def _boot(label: str, fn: Callable[[], Any]) -> None:
    try:
        fn()
        print(f"[JARVIS] {label}", flush=True)
    except Exception as e:
        _log.exception("background boot failed: %s", label)
        print(f"[JARVIS] {label} skip: {e}", flush=True)
        try:
            from core import audit as _audit
            if _audit:
                _audit.record("background_boot_fail", {"label": label, "error": str(e)[:200]})
        except Exception:
            pass


def start_all(player: Any = None) -> None:
    """Start 24/7 daemon workers. Never raises."""
    def _kaggle():
        from actions.ai_core._kaggle_datasets_impl import ensure_kaggle_credentials
        ensure_kaggle_credentials()

    def _tg():
        from actions.web_media._telegram_commander_impl import start_listener
        if start_listener(player=player):
            print("[JARVIS] Telegram commander ativo (chat autorizado).")
        else:
            print("[JARVIS] Telegram commander: token/chat não configurados.")

    def _pwr():
        from actions.security._anti_sabotagem_energia_impl import start_monitor as _m
        _m()

    def _lem():
        from actions.productivity._lembretes_persistentes_impl import start_scheduler as _m
        _m(player=player)

    def _bak():
        from actions.productivity._backup_nuvem_impl import start_scheduler as _m
        _m(player=player)

    def _ofertas():
        from actions.finance_shopping._cacador_ofertas_impl import start_scheduler as _m
        _m(player=player)

    def _night():
        from actions.ai_core._engenheiro_noturno_impl import start_scheduler as _m
        _m(player=player)

    def _clima():
        from actions.web_media._radar_climatico_rp_impl import start_monitor as _m
        _m(player=player)

    def _diario():
        from actions.ai_core._diario_cognitivo_impl import start_scheduler as _m
        _m(player=player)

    def _watchdog():
        import os as _os
        if (_os.getenv("WATCHDOG_INTERNET_AUTO") or "").strip().lower() in ("1", "true", "yes"):
            import actions.productivity.daily_ops as daily_ops
            daily_ops.daily_ops(parameters={"action": "watchdog_start"}, player=player)
            print("[JARVIS] Internet watchdog iniciado (WATCHDOG_INTERNET_AUTO).")

    def _mcp():
        from core.mcp_client import boot_mcp_async
        boot_mcp_async(timeout=8.0)

    def _heal():
        from actions.system._self_healing import start_watchdog
        start_watchdog()

    _boot("Self-healing watchdog", _heal)
    _boot("MCP servers", _mcp)
    _boot("Kaggle credentials", _kaggle)
    _boot("Telegram commander", _tg)
    _boot("Anti-sabotagem energia", _pwr)
    _boot("Lembretes scheduler", _lem)
    _boot("Backup semanal", _bak)
    _boot("Caçador de ofertas", _ofertas)
    _boot("Engenheiro noturno", _night)
    _boot("Radar climático Rio Preto", _clima)
    _boot("Diário cognitivo", _diario)
    _boot("Watchdog internet", _watchdog)


__all__ = ["start_all"]
