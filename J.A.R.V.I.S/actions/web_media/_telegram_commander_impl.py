"""telegram_commander — texto + voz; só TELEGRAM_CHAT_ID; integra audio_channel."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.outcome import done
from actions.security._security_vision import audit, connect_icsee_and_capture, send_telegram, speak_short

_BASE = Path(__file__).resolve().parents[2]
_TMP_OGG = _BASE / "memory" / "tmp_tg_voice.ogg"
_TMP_WAV = _BASE / "memory" / "tmp_tg_voice.wav"
_TMP_REPLY = _BASE / "memory" / "tmp_tg_reply.wav"

_state: dict[str, Any] = {
    "thread": None,
    "stop": threading.Event(),
    "offset": 0,
    "player": None,
}
_lock = threading.Lock()


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d or "").strip()


def _token() -> str:
    return _env("TELEGRAM_BOT_TOKEN")


def _chat_ok(chat_id) -> bool:
    allowed = _env("TELEGRAM_CHAT_ID")
    return bool(allowed) and str(chat_id).strip() == allowed.strip()


def _api(method: str, payload: Optional[dict] = None, timeout: float = 35) -> dict:
    import requests
    r = requests.post(
        f"https://api.telegram.org/bot{_token()}/{method}",
        json=payload or {},
        timeout=timeout,
    )
    try:
        return r.json()
    except Exception:
        return {"ok": False}


def _reply(chat_id: str, text: str, markdown: bool = True) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": (text or "")[:4000]}
    if markdown:
        payload["parse_mode"] = "Markdown"
    try:
        _api("sendMessage", payload, timeout=(4, 12))
    except Exception as e:
        audit("tg_reply_fail", tool="telegram_commander", extra={"error": str(e)[:120]})


def _download_tg_file(file_id: str, dest: Path) -> bool:
    import requests
    meta = _api("getFile", {"file_id": file_id}, timeout=(4, 15))
    fpath = ((meta.get("result") or {}).get("file_path")) if meta.get("ok") else None
    if not fpath:
        return False
    url = f"https://api.telegram.org/file/bot{_token()}/{fpath}"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=(4, 45))
        if r.status_code != 200:
            return False
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        audit("tg_download_fail", tool="telegram_commander", extra={"error": str(e)[:120]})
        return False


def _ogg_to_wav(src: Path, dst: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
            capture_output=True,
            timeout=30,
        )
        return dst.is_file() and dst.stat().st_size > 0
    except Exception:
        pass
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(src))
        audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(str(dst), format="wav")
        return dst.is_file()
    except Exception as e:
        audit("tg_convert_fail", tool="telegram_commander", extra={"error": str(e)[:120]})
        return False


def _transcribe_wav(path: Path) -> str:
    # Prefer faster-whisper / providers
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(path), language="pt")
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            return text
    except Exception as e:
        audit("tg_stt_fw_fail", tool="telegram_commander", extra={"error": str(e)[:100]})
    try:
        import numpy as np
        import soundfile as sf
        from core.stt import WhisperSTT
        data, sr = sf.read(str(path), dtype="float32")
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        stt = WhisperSTT(model_name="base", language="pt")
        return (stt.transcribe(np.asarray(data)) or "").strip()
    except Exception as e:
        audit("tg_stt_core_fail", tool="telegram_commander", extra={"error": str(e)[:100]})
    return ""


def _tts_to_wav(text: str, dest: Path) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Try piper CLI / engine file output; fallback: skip voice reply
    try:
        from core import tts as tts_mod
        # Prefer engines with file synthesis if available
        player = getattr(tts_mod, "TTSPlayer", None)
        if player:
            # speak to default device only as last resort — for file, use edge/piper if present
            pass
    except Exception:
        pass
    try:
        # edge-tts to mp3 then ffmpeg wav
        import asyncio
        import edge_tts
        mp3 = dest.with_suffix(".mp3")

        async def _gen():
            communicate = edge_tts.Communicate(text[:500], voice="pt-BR-AntonioNeural")
            await communicate.save(str(mp3))

        asyncio.run(_gen())
        if mp3.is_file():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(dest)],
                capture_output=True,
                timeout=30,
            )
            mp3.unlink(missing_ok=True)
            return dest.is_file()
    except Exception as e:
        audit("tg_tts_edge_fail", tool="telegram_commander", extra={"error": str(e)[:100]})
    try:
        # pyttsx3 offline
        import pyttsx3
        eng = pyttsx3.init()
        eng.save_to_file(text[:500], str(dest))
        eng.runAndWait()
        return dest.is_file()
    except Exception as e:
        audit("tg_tts_fail", tool="telegram_commander", extra={"error": str(e)[:100]})
        return False


def _send_voice(chat_id: str, wav_path: Path, caption: str = "") -> None:
    import requests
    if not wav_path.is_file():
        return
    # Telegram prefers ogg/opus for voice; send as document/audio if convert fails
    ogg = wav_path.with_suffix(".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libopus", str(ogg)],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        ogg = wav_path
    try:
        with open(ogg, "rb") as fh:
            requests.post(
                f"https://api.telegram.org/bot{_token()}/sendVoice",
                data={"chat_id": chat_id, "caption": caption[:200]},
                files={"voice": fh},
                timeout=(4, 45),
            )
    except Exception as e:
        audit("tg_send_voice_fail", tool="telegram_commander", extra={"error": str(e)[:120]})


def _route_natural_language(text: str, chat_id: str, *, from_voice: bool = False) -> None:
    """Map spoken/typed natural language to tools; always allow /190 style intents."""
    low = (text or "").strip().lower()
    if not low:
        _reply(chat_id, "Não entendi o áudio, Senhor.")
        return

    # Audio channel phrases
    if any(x in low for x in ("modo rua", "áudio para o telegram", "audio para o telegram", "pausar microfone")):
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "telegram"}, player=_state.get("player"))
        _reply(chat_id, "*Modo rua*\n`" + str(r)[:300] + "`")
        return
    if any(x in low for x in ("modo casa", "voltar áudio", "voltar audio", "microfone local")):
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "casa"}, player=_state.get("player"))
        _reply(chat_id, "*Modo casa*\n`" + str(r)[:300] + "`")
        return
    if "híbrid" in low or "hibrid" in low:
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "hibrido"}, player=_state.get("player"))
        _reply(chat_id, "*Modo híbrido*\n`" + str(r)[:300] + "`")
        return

    # Critical: 190 always, silent at home
    if "protocolo 190" in low or low.strip() in ("190", "ativar protocolo 190"):
        import actions.productivity.protocolo as protocolo
        r = protocolo.protocolo(parameters={"action": "ativar", "nome": "190"})
        _reply(chat_id, "*Protocolo 190* executado em silêncio.\n`" + str(r)[:400] + "`")
        return

    if "protocolo demo" in low or "ativar protocolo demo" in low:
        import actions.productivity.protocolo as protocolo
        r = protocolo.protocolo(parameters={"action": "ativar", "nome": "demo"}, player=_state.get("player"))
        _reply(chat_id, "*Demo*\n`" + str(r)[:400] + "`")
        if from_voice:
            _maybe_voice_reply(chat_id, "Demonstração concluída, Senhor.")
        return

    if any(x in low for x in ("câmeras", "cameras", "como estão as câmeras", "como estao as cameras")):
        _cmd_cameras(chat_id)
        if from_voice:
            _maybe_voice_reply(chat_id, "Enviei a captura das câmeras, Senhor.")
        return

    # Fallback: echo transcription + brief acknowledgment
    _reply(chat_id, f"*Transcrição*\n{text}\n\n_Comando não mapeado — use /help._")
    if from_voice:
        _maybe_voice_reply(chat_id, "Recebi seu áudio, Senhor. Use um comando da lista de ajuda se preferir.")


def _maybe_voice_reply(chat_id: str, text: str) -> None:
    try:
        from actions.system._audio_channel_impl import telegram_audio_enabled
        if not telegram_audio_enabled():
            return
    except Exception:
        pass
    if _tts_to_wav(text, _TMP_REPLY):
        _send_voice(chat_id, _TMP_REPLY)


def _cmd_cameras(chat_id: str) -> None:
    cap = connect_icsee_and_capture(player=None, load_delay=2.0)
    if cap.get("ok") and cap.get("path"):
        send_telegram("*Câmeras iCSee* — captura ao vivo.", cap["path"], markdown=True)
    else:
        _reply(chat_id, f"Falha na captura: `{cap.get('reason')}`")


def _handle(text: str, chat_id: str, *, from_voice: bool = False) -> None:
    low = (text or "").strip().lower()

    # Slash commands
    if low.startswith("/cameras"):
        _cmd_cameras(chat_id)
        return
    if low.startswith("/status"):
        try:
            import actions.system.system_health as system_health
            raw = str(system_health.system_health(parameters={"action": "status"}))
            _reply(chat_id, f"*Status do sistema*\n```\n{raw[:3000]}\n```")
        except Exception as e:
            _reply(chat_id, f"Erro de status: `{e}`")
        return
    if low.startswith("/falar") or low.startswith("/say"):
        parts = text.split(None, 1)
        msg = parts[1] if len(parts) > 1 else ""
        if not msg:
            _reply(chat_id, "Uso: `/falar <texto>`")
            return
        # House speakers only if local mic mode allows local output
        try:
            from actions.system._audio_channel_impl import local_mic_enabled
            silent = not local_mic_enabled()
        except Exception:
            silent = False
        speak_short(msg, player=_state.get("player"), silent=silent)
        _reply(chat_id, "Mensagem processada, Senhor.")
        return
    
    
    if low.startswith("/simular_invasao") or low.startswith("/simular"):
        from actions.security._security_vision import simulate_invasion_scan
        r = simulate_invasion_scan(player=_state.get("player"))
        an = (r.get("analysis") or {})
        _reply(
            chat_id,
            f"*Simulação invasão* — *{an.get('classificacao')}* (risco {an.get('nivel_risco')})\n"
            f"{an.get('descricao_tatica')}",
        )
        return
    if low.startswith("/baixar_kaggle"):
        import actions.ai_core.kaggle_datasets as kaggle_datasets
        r = kaggle_datasets.kaggle_datasets(parameters={"action": "download_burglary"}, player=_state.get("player"))
        _reply(chat_id, "*Kaggle Burglary*\n`" + str(r)[:800] + "`")
        return

    
    if low.startswith("/placa"):
        import actions.security.leitor_placas_alpr as leitor_placas_alpr
        r = leitor_placas_alpr.leitor_placas_alpr(parameters={"action": "read"}, player=_state.get("player"))
        _reply(chat_id, "*Placa / portão*\n`" + str(r)[:800] + "`")
        return
    if low.startswith("/clima") or low.startswith("/chuva"):
        from .radar_climatico_rp import radar_climatico_rp
        r = radar_climatico_rp(parameters={"action": "check_now"}, player=_state.get("player"))
        _reply(chat_id, "*Radar climático RP*\n`" + str(r)[:800] + "`")
        return

    
    
    if low.startswith("/mover_download") or low.startswith("/mover_downloads"):
        parts = text.split()
        fname = parts[1] if len(parts) > 1 else ""
        dest = parts[2] if len(parts) > 2 else "root"
        import actions.productivity.mover_downloads as mover_downloads
        r = mover_downloads.mover_downloads(
            parameters={"action": "move", "filename": fname, "destination": dest},
            player=_state.get("player"),
        )
        _reply(chat_id, "*Mover Downloads*\n`" + str(r)[:800] + "`")
        return

    if low.startswith("/offline"):
        import actions.ai_core.offline as offline
        r = offline.offline(parameters={"action": "enable"}, player=_state.get("player"))
        _reply(chat_id, "*Modo offline*\n`" + str(r)[:500] + "`")
        return
    if low.startswith("/online"):
        import actions.ai_core.offline as offline
        r = offline.offline(parameters={"action": "disable"}, player=_state.get("player"))
        _reply(chat_id, "*Modo online*\n`" + str(r)[:500] + "`")
        return
    if low.startswith("/preparar_offline"):
        import actions.ai_core.offline as offline
        r = offline.offline(parameters={"action": "prepare"}, player=_state.get("player"))
        _reply(chat_id, "*Preparar offline*\n`" + str(r)[:800] + "`")
        return
    if low.startswith("/mcp"):
        import actions.ai_core.mcp_manager as mcp_manager
        r = mcp_manager.mcp_manager(parameters={"action": "list"}, player=_state.get("player"))
        _reply(chat_id, "*MCP*\n`" + str(r)[:1200] + "`")
        return

    if low.startswith("/analisar") or low.startswith("/perimetro") or low.startswith("/perímetro"):
        from actions.security._security_vision import run_perimeter_scan
        r = run_perimeter_scan(player=_state.get("player"), announce=False)
        an = (r.get("analysis") or {})
        _reply(
            chat_id,
            f"*Perímetro* — *{an.get('classificacao')}* (risco {an.get('nivel_risco')})\n"
            f"{an.get('evolucao_movimento')}\n{an.get('descricao_tatica')}",
        )
        return
    if low.startswith("/senha"):
        from core.owner_gate import password_ok
        parts = text.split(None, 1)
        pw = parts[1].strip() if len(parts) > 1 else ""
        ok = password_ok(pw)
        _reply(chat_id, "Senha aceita." if ok else "Senha inválida.")
        return

    if low.startswith("/190"):
        import actions.productivity.protocolo as protocolo
        r = protocolo.protocolo(parameters={"action": "ativar", "nome": "190"})
        _reply(chat_id, "*Protocolo 190* executado em silêncio.\n`" + str(r)[:500] + "`")
        return
    if low.startswith("/demo"):
        import actions.productivity.protocolo as protocolo
        r = protocolo.protocolo(parameters={"action": "ativar", "nome": "demo"}, player=_state.get("player"))
        _reply(chat_id, "*Protocolo demo* concluído.\n`" + str(r)[:500] + "`")
        return
    if low.startswith("/modo_rua") or low.startswith("/audio_telegram"):
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "telegram"}, player=_state.get("player"))
        _reply(chat_id, "*Modo rua (Telegram)*\n`" + str(r)[:400] + "`")
        return
    if low.startswith("/modo_casa") or low.startswith("/audio_cell"):
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "casa"}, player=_state.get("player"))
        _reply(chat_id, "*Modo casa*\n`" + str(r)[:400] + "`")
        return
    if low.startswith("/audio_hibrido"):
        import actions.system.audio_channel as audio_channel
        r = audio_channel.audio_channel(parameters={"action": "hibrido"}, player=_state.get("player"))
        _reply(chat_id, "*Modo híbrido*\n`" + str(r)[:400] + "`")
        return
    if low.startswith("/dissuasao"):
        import actions.security.protocolo_dissuasao as protocolo_dissuasao
        r = protocolo_dissuasao.protocolo_dissuasao(parameters={"action": "ativar"}, player=_state.get("player"))
        _reply(chat_id, "*Dissuasão* acionada.\n`" + str(r)[:400] + "`")
        return
    if low.startswith("/gravar"):
        import actions.security.gravador_caixa_preta as gravador_caixa_preta
        act = "stop" if "parar" in low or "stop" in low else "start"
        r = gravador_caixa_preta.gravador_caixa_preta(parameters={"action": act})
        _reply(chat_id, f"*Caixa-preta* `{act}`\n`" + str(r)[:300] + "`")
        return
    if low.startswith("/viagem"):
        import actions.smarthome.simulador_presenca as simulador_presenca
        r = simulador_presenca.simulador_presenca(parameters={"action": "start"})
        _reply(chat_id, "*Simulador de presença*\n`" + str(r)[:300] + "`")
        return
    if low.startswith("/lista"):
        import actions.finance_shopping.lista_compras as lista_compras
        r = lista_compras.lista_compras(parameters={"action": "list"})
        _reply(chat_id, "*Lista de compras*\n`" + str(r)[:800] + "`")
        return
    if low.startswith("/gastos"):
        import actions.finance_shopping.controle_gastos as controle_gastos
        r = controle_gastos.controle_gastos(parameters={"action": "month"})
        _reply(chat_id, "*Gastos do mês*\n`" + str(r)[:500] + "`")
        return
    if low.startswith("/tela"):
        import actions.system.remote_pc_admin as remote_pc_admin
        r = remote_pc_admin.remote_pc_admin(parameters={"action": "screenshot"})
        _reply(chat_id, "*Tela*\n`" + str(r)[:300] + "`")
        return
    if low.startswith("/processos"):
        import actions.system.remote_pc_admin as remote_pc_admin
        r = remote_pc_admin.remote_pc_admin(parameters={"action": "processes"})
        _reply(chat_id, "*Top processos*\n`" + str(r)[:800] + "`")
        return
    if low.startswith("/reiniciar"):
        import actions.system.remote_pc_admin as remote_pc_admin
        r = remote_pc_admin.remote_pc_admin(parameters={"action": "reboot"})
        _reply(chat_id, "*Reinício*\n`" + str(r)[:300] + "`")
        return
    if low.startswith("/cmd"):
        import actions.system.remote_pc_admin as remote_pc_admin
        cmd = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        r = remote_pc_admin.remote_pc_admin(parameters={"action": "cmd", "command": cmd})
        _reply(chat_id, "*CMD*\n```\n" + str(r)[:3000] + "\n```")
        return
    if low.startswith("/backup"):
        import actions.productivity.backup_nuvem as backup_nuvem
        r = backup_nuvem.backup_nuvem(parameters={"action": "now"})
        _reply(chat_id, "*Backup*\n`" + str(r)[:400] + "`")
        return
    if low in ("/help", "/start", "help"):
        help_txt = (
            "*J.A.R.V.I.S. — remoto*" + chr(10)
            + "`/cameras` `/status` `/falar` `/190` `/demo`" + chr(10)
            + "`/modo_rua` `/modo_casa` `/audio_hibrido` `/analisar` `/simular_invasao` `/baixar_kaggle` `/senha`" + chr(10)
            + "`/dissuasao` `/gravar` `/viagem` `/lista` `/gastos`" + chr(10)
            + "`/tela` `/processos` `/reiniciar` `/cmd` `/backup`" + chr(10)
            + "_Envie também mensagens de voz._"
        )
        _reply(chat_id, help_txt)
        return

    # Natural language (including voice transcriptions)
    if low.startswith("/"):
        _reply(chat_id, "Comando não reconhecido. Use `/help`.")
        return
    _route_natural_language(text, chat_id, from_voice=from_voice)


def _handle_voice_message(msg: dict, chat_id: str) -> None:
    voice = msg.get("voice") or msg.get("audio") or {}
    file_id = voice.get("file_id")
    if not file_id:
        _reply(chat_id, "Áudio sem file_id.")
        return
    if not _download_tg_file(file_id, _TMP_OGG):
        _reply(chat_id, "Falha ao baixar o áudio, Senhor.")
        return
    if not _ogg_to_wav(_TMP_OGG, _TMP_WAV):
        _reply(chat_id, "Falha ao converter o áudio (ffmpeg/pydub).")
        return
    text = _transcribe_wav(_TMP_WAV)
    if not text:
        _reply(chat_id, "Não consegui transcrever o áudio, Senhor.")
        return
    _reply(chat_id, f"*Você disse:*\n_{text}_")
    # 190 must run even in modo_rua — handled inside _handle / route
    _handle(text, chat_id, from_voice=True)


def _poll_loop() -> None:
    print("[telegram_commander] polling started (text+voice)")
    while not _state["stop"].is_set():
        try:
            if not _token() or not _env("TELEGRAM_CHAT_ID"):
                time.sleep(5)
                continue
            data = _api(
                "getUpdates",
                {"offset": _state["offset"], "timeout": 25, "allowed_updates": ["message", "callback_query"]},
                timeout=(4, 30),
            )
            for upd in data.get("result") or []:
                _state["offset"] = int(upd.get("update_id", 0)) + 1
                msg = upd.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                if not _chat_ok(chat_id):
                    continue
                try:
                    if msg.get("voice") or msg.get("audio"):
                        _handle_voice_message(msg, str(chat_id))
                    else:
                        text = msg.get("text") or ""
                        if text:
                            _handle(text, str(chat_id), from_voice=False)
                except Exception as e:
                    audit("tg_handle_fail", tool="telegram_commander", extra={"error": str(e)[:140]})
        except Exception as e:
            audit("tg_poll_fail", tool="telegram_commander", extra={"error": str(e)[:140]})
            time.sleep(3)
    print("[telegram_commander] polling stopped")


def start_listener(player=None) -> bool:
    if not _token() or not _env("TELEGRAM_CHAT_ID"):
        return False
    with _lock:
        _state["player"] = player
        if _state["thread"] and _state["thread"].is_alive():
            return True
        _state["stop"] = threading.Event()
        t = threading.Thread(target=_poll_loop, daemon=True, name="telegram-commander")
        _state["thread"] = t
        t.start()
    # restore audio channel state
    try:
        from actions.system._audio_channel_impl import get_mode, apply_mode
        apply_mode(get_mode(), player=player)
    except Exception:
        pass
    return True


def stop_listener() -> None:
    _state["stop"].set()
    if _state.get("thread"):
        _state["thread"].join(timeout=2)


def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action == "start":
        return done("telegram_commander", action="start", running=start_listener(player))
    if action == "stop":
        stop_listener()
        return done("telegram_commander", action="stop", running=False)
    alive = bool(_state["thread"] and _state["thread"].is_alive())
    return done(
        "telegram_commander",
        action="status",
        running=alive,
        configured=bool(_token() and _env("TELEGRAM_CHAT_ID")),
    )
