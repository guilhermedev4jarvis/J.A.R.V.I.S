#!/usr/bin/env python3
"""Migrate flat actions/*.py into domain subpackages and rewrite imports."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "actions"

# Explicit domain mapping (stem without .py)
MAP: dict[str, str] = {
    # security
    "intruder_alert": "security", "_intruder_alert_impl": "security",
    "_security_vision": "security", "leitor_placas_alpr": "security",
    "_leitor_placas_alpr_impl": "security", "network_guard": "security",
    "_network_guard_impl": "security", "_porteiro_inteligente": "security",
    "_face_whitelist": "security", "anti_sabotagem_energia": "security",
    "_anti_sabotagem_energia_impl": "security", "protocolo_dissuasao": "security",
    "_protocolo_dissuasao_impl": "security", "gravador_caixa_preta": "security",
    "_gravador_caixa_preta_impl": "security", "sentinel_patrol": "security",
    "_sentinel_patrol_impl": "security", "secure_vault_helper": "security",
    "_secure_vault_helper_impl": "security",
    # smarthome
    "smart_home": "smarthome", "_smart_home_impl": "smarthome",
    "_smart_climate": "smarthome",
    "simulador_presenca": "smarthome", "_simulador_presenca_impl": "smarthome",
    "controle_media_casa": "smarthome", "_controle_media_casa_impl": "smarthome",
    # system
    "computer_settings": "system", "_computer_control_impl": "system",
    "process_manager": "system", "system_health": "system", "_system_health_impl": "system",
    "system_resources_monitor": "system", "_system_resources_monitor_impl": "system",
    "_system_monitor_impl": "system", "resource_governor": "system",
    "_resource_governor_impl": "system", "power_profile_manager": "system",
    "_power_profile_manager_impl": "system", "hwmonitor_integration": "system",
    "_hwmonitor_integration_impl": "system", "battery": "system",
    "audio_channel": "system", "_audio_channel_impl": "system",
    "app_audio_mixer": "system", "_app_audio_mixer_impl": "system",
    "audio_latency_tuner": "system", "network_manager": "system",
    "network_status": "system", "_network_status_impl": "system",
    "radar_dispositivos_wifi": "system", "_radar_dispositivos_wifi_impl": "system",
    "remote_pc_admin": "system", "_remote_pc_admin_impl": "system",
    "_powershell_assist_impl": "system", "_powershell_cmd_impl": "system",
    "dependency_health": "system", "_self_healing": "system", "hot_reload": "system",
    # desktop
    "desktop_agent": "desktop", "_desktop_agent_impl": "desktop",
    "desktop_control": "desktop", "_desktop_impl": "desktop",
    "window_manager": "desktop", "_window_manager_impl": "desktop",
    "clipboard_smart": "desktop", "_clipboard_smart_impl": "desktop",
    "open_app": "desktop", "screen_processor": "desktop", "screenshot_ocr": "desktop",
    "screen_context_advisor": "desktop", "_screen_context_advisor_impl": "desktop",
    "image_upscale": "desktop", "guardiao_postura": "desktop",
    "_guardiao_postura_impl": "desktop",
    # productivity
    "reminder": "productivity", "lembretes_persistentes": "productivity",
    "_lembretes_persistentes_impl": "productivity", "meeting_brief": "productivity",
    "meeting_transcriber": "productivity", "_meeting_transcriber_impl": "productivity",
    "quick_note": "productivity", "focus_timer": "productivity",
    "modo_foco": "productivity", "_modo_foco_impl": "productivity",
    "file_manager": "productivity", "file_organize": "productivity",
    "_file_organize_impl": "productivity", "mover_downloads": "productivity",
    "_mover_downloads_impl": "productivity", "baixar_arquivo": "productivity",
    "backup_nuvem": "productivity", "_backup_nuvem_impl": "productivity",
    "escritorio_documentos": "productivity", "_escritorio_documentos_impl": "productivity",
    "routine_orchestrator": "productivity", "_routine_orchestrator_impl": "productivity",
    "daily_ops": "productivity", "_daily_ops_impl": "productivity",
    "protocolo": "productivity", "_protocolo_impl": "productivity",
    "email_triage": "productivity",
    # web_media
    "browser_control": "web_media", "whatsapp_web": "web_media",
    "send_message": "web_media", "telegram_commander": "web_media",
    "_telegram_commander_impl": "web_media", "youtube_video": "web_media",
    "video_player": "web_media", "media_control": "web_media",
    "web_search": "web_media", "deep_research": "web_media",
    "noticias_brasil": "web_media", "weather_report": "web_media",
    "radar_climatico_rp": "web_media", "_radar_climatico_rp_impl": "web_media",
    "curador_nicho": "web_media", "_curador_nicho_impl": "web_media",
    "entretenimento_familia": "web_media", "_entretenimento_familia_impl": "web_media",
    "webhook_bridge": "web_media", "_webhook_bridge_impl": "web_media",
    # finance_shopping
    "controle_gastos": "finance_shopping", "_controle_gastos_impl": "finance_shopping",
    "_finance_audit": "finance_shopping", "bank_statement": "finance_shopping",
    "cotacao_dolar": "finance_shopping", "cacador_ofertas": "finance_shopping",
    "_cacador_ofertas_impl": "finance_shopping", "lista_compras": "finance_shopping",
    "_lista_compras_impl": "finance_shopping", "unit_convert": "finance_shopping",
    # ai_core
    "mission_planner": "ai_core", "_mission_planner_impl": "ai_core",
    "self_program": "ai_core", "_self_program_impl": "ai_core",
    "_dev_agent_impl": "ai_core", "engenheiro_noturno": "ai_core",
    "_engenheiro_noturno_impl": "ai_core", "code_studio": "ai_core",
    "mcp_manager": "ai_core", "_mcp_manager_impl": "ai_core",
    "local_doc_rag": "ai_core", "_local_doc_rag_impl": "ai_core",
    "memory_compactor": "ai_core", "diario_cognitivo": "ai_core",
    "_diario_cognitivo_impl": "ai_core", "mestre_feynman": "ai_core",
    "_mestre_feynman_impl": "ai_core", "tutor_conversacao": "ai_core",
    "_tutor_conversacao_impl": "ai_core", "ai_collaboration": "ai_core",
    "kaggle_datasets": "ai_core", "_kaggle_datasets_impl": "ai_core",
    "proactive": "ai_core", "context_triggers": "ai_core",
    "_context_triggers_impl": "ai_core", "agent_mode_control": "ai_core",
    "owner_setup": "ai_core", "action_analytics": "ai_core",
    "offline": "ai_core", "_offline_impl": "ai_core",
    "_background_monitor_impl": "ai_core", "_presence_travel": "ai_core",
}

DEFAULT_PKG = "misc"

# Heuristic for remaining stems
def guess_pkg(stem: str) -> str:
    if stem in MAP:
        return MAP[stem]
    s = stem.lower()
    if any(k in s for k in ("security", "intruder", "sentinel", "porteiro", "placa", "alpr", "face", "vault", "dissuas", "caixa_preta", "network_guard")):
        return "security"
    if any(k in s for k in ("smart_home", "climate", "presenca", "media_casa", "tuya")):
        return "smarthome"
    if any(k in s for k in ("system", "process", "resource", "power", "battery", "audio", "network", "wifi", "powershell", "dependency", "healing", "hwmonitor", "computer", "remote_pc")):
        return "system"
    if any(k in s for k in ("desktop", "window", "clipboard", "open_app", "screen", "screenshot", "image_upscale", "postura")):
        return "desktop"
    if any(k in s for k in ("reminder", "lembrete", "meeting", "note", "focus", "file_", "download", "backup", "escritorio", "routine", "daily", "protocolo", "email")):
        return "productivity"
    if any(k in s for k in ("browser", "whatsapp", "telegram", "youtube", "video", "media", "web_search", "research", "noticia", "weather", "radar_clim", "curador", "entretenimento", "webhook", "send_message")):
        return "web_media"
    if any(k in s for k in ("gasto", "finance", "bank", "dolar", "oferta", "compra", "lista_compra", "unit_convert", "cotacao")):
        return "finance_shopping"
    if any(k in s for k in ("mission", "program", "code", "mcp", "rag", "memory", "diario", "feynman", "tutor", "ai_", "kaggle", "proactive", "context", "agent", "owner", "offline", "background", "presence", "collaboration", "analytics", "dev_agent", "engenheiro")):
        return "ai_core"
    if any(k in s for k in ("game", "roblox", "blender", "godot")):
        return "misc"
    return DEFAULT_PKG


def rewrite_text(text: str, stem_to_pkg: dict[str, str]) -> str:
    # patch("actions.foo...") and import paths
    def abs_mod(stem: str) -> str:
        pkg = stem_to_pkg.get(stem)
        return f"actions.{pkg}.{stem}" if pkg else f"actions.{stem}"

    # from actions.X import / import actions.X
    def repl_from(m: re.Match) -> str:
        stem = m.group(1)
        rest = m.group(2) or ""
        if stem in stem_to_pkg:
            return f"from {abs_mod(stem)}{rest}"
        return m.group(0)

    text = re.sub(r"\bfrom\s+actions\.([A-Za-z_][A-Za-z0-9_]*)(\s+import\b)", repl_from, text)

    def repl_import(m: re.Match) -> str:
        stem = m.group(1)
        if stem in stem_to_pkg:
            return f"import {abs_mod(stem)}"
        return m.group(0)

    text = re.sub(r"\bimport\s+actions\.([A-Za-z_][A-Za-z0-9_]*)\b", repl_import, text)

    # patch / monkeypatch strings
    def repl_patch(m: re.Match) -> str:
        stem = m.group(1)
        tail = m.group(2) or ""
        if stem in stem_to_pkg:
            return f"{m.group(0)[: m.start(1) - m.start()]}{abs_mod(stem)}{tail}"
        # safer: reconstruct
        quote = m.group(0)[0]
        return f"{quote}{abs_mod(stem)}{tail}{quote}" if stem in stem_to_pkg else m.group(0)

    text = re.sub(
        r"""(['\"])actions\.([A-Za-z_][A-Za-z0-9_]*)([^'\"]*)\1""",
        lambda m: f"{m.group(1)}{abs_mod(m.group(2))}{m.group(3)}{m.group(1)}"
        if m.group(2) in stem_to_pkg
        else m.group(0),
        text,
    )
    return text


def relative_rewrite_in_package(text: str, pkg: str, stem_to_pkg: dict[str, str]) -> str:
    """Inside actions/<pkg>/ prefer relative imports for same package."""
    # from actions.pkg.X import -> from .X import
    text = re.sub(
        rf"\bfrom\s+actions\.{re.escape(pkg)}\.([A-Za-z_][A-Za-z0-9_]*)\s+import\b",
        r"from .\1 import",
        text,
    )
    # from actions._foo_impl import when _foo is same pkg
    def rel_priv(m: re.Match) -> str:
        stem = m.group(1)
        if stem_to_pkg.get(stem) == pkg:
            return f"from .{stem} import"
        if stem in stem_to_pkg:
            return f"from actions.{stem_to_pkg[stem]}.{stem} import"
        return m.group(0)

    text = re.sub(r"\bfrom\s+actions\.([A-Za-z_][A-Za-z0-9_]*)\s+import\b", rel_priv, text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dry = not args.apply

    root_files = sorted(
        p for p in ACTIONS.glob("*.py") if p.name != "__init__.py" and p.is_file()
    )
    stem_to_pkg: dict[str, str] = {}
    for p in root_files:
        stem_to_pkg[p.stem] = guess_pkg(p.stem)

    packages = sorted(set(stem_to_pkg.values()) | set(MAP.values()) | {DEFAULT_PKG})
    print(f"files={len(root_files)} packages={packages}")

    for pkg in packages:
        d = ACTIONS / pkg
        print(("PLAN mkdir" if dry else "MKDIR"), d.relative_to(ROOT))
        if not dry:
            d.mkdir(parents=True, exist_ok=True)
            init = d / "__init__.py"
            if not init.exists():
                init.write_text(f'"""actions.{pkg} — domain package."""\n', encoding="utf-8")

    moves: list[tuple[Path, Path, str]] = []
    for src in root_files:
        pkg = stem_to_pkg[src.stem]
        dest = ACTIONS / pkg / src.name
        moves.append((src, dest, pkg))
        print(("PLAN move" if dry else "MOVE"), src.name, "->", dest.relative_to(ROOT))

    if dry:
        print("Dry-run only. Re-run with --apply")
        return 0

    for src, dest, pkg in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    # rewrite all python under project for absolute paths
    skip_parts = {".venv", "__pycache__", ".git", ".pytest_cache"}
    for py in ROOT.rglob("*.py"):
        if any(part in skip_parts for part in py.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        new = rewrite_text(text, stem_to_pkg)
        # relative inside domain packages
        try:
            rel = py.relative_to(ACTIONS)
            if len(rel.parts) >= 2:
                pkg = rel.parts[0]
                if pkg in packages:
                    new = relative_rewrite_in_package(new, pkg, stem_to_pkg)
        except ValueError:
            pass
        if new != text:
            py.write_text(new, encoding="utf-8")
            print("REWRITE", py.relative_to(ROOT))

    # ensure root actions/__init__.py exists
    init_root = ACTIONS / "__init__.py"
    if not init_root.exists():
        init_root.write_text('"""J.A.R.V.I.S. actions package (domain subpackages)."""\n', encoding="utf-8")

    left = [p.name for p in ACTIONS.glob("*.py") if p.name != "__init__.py"]
    print("left_on_root", left)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
