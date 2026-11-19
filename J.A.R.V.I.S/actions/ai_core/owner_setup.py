"""
owner_setup — first-run enrollment of owner voice + 3 face photos + command phrase.

Files produced under memory/biometrics/:
  vozdono.mp3, fotobase1.jpg, fotobase2.jpg, fotobase3.jpg, owner_command.json
"""
from __future__ import annotations

from core.outcome import done, failed, ask
from core import owner_gate


def owner_setup(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    if action in ("status", "check", ""):
        st = owner_gate.enrollment_status()
        return done(
            "owner_setup",
            action="status",
            complete=st["complete"],
            voice=st["voice"],
            faces_ok=st["faces_ok"],
            faces=str(st["faces"]),
            phrase=st.get("phrase") or "",
            message=owner_gate.enrollment_prompt_pt(),
        )

    if action in ("set_phrase", "phrase", "command"):
        phrase = str(params.get("phrase") or params.get("command") or "").strip()
        if not phrase:
            return ask(
                "owner_setup",
                "qual frase de comando do dono?",
                examples="ok jarvis | acorda jarvis | hey mark",
            )
        data = owner_gate.save_command_phrase(phrase)
        return done("owner_setup", action="set_phrase", phrase=data["phrase"])

    if action in ("enroll_voice", "voice"):
        path = params.get("wav_path") or params.get("path") or params.get("audio_path")
        if not path:
            return ask(
                "owner_setup",
                "caminho do áudio da sua voz (wav/mp3) dizendo o comando?",
                save_as="memory/biometrics/vozdono.mp3",
            )
        phrase = params.get("phrase") or params.get("command")
        try:
            info = owner_gate.register_voice_file(path, phrase=phrase)
            return done("owner_setup", action="enroll_voice", **{
                k: info.get(k) for k in info if k in ("command", "files")
            }, fingerprint=str(info.get("voice")))
        except Exception as e:
            return failed("owner_setup", f"voice enroll failed: {e}")

    if action in ("enroll_face", "face"):
        slot = params.get("slot") or params.get("photo")
        try:
            slot_i = int(slot)
        except (TypeError, ValueError):
            return ask("owner_setup", "slot da foto? 1=frente, 2=lado A, 3=lado B")
        path = params.get("image_path") or params.get("path")
        camera = str(params.get("camera") or "").lower() in ("1", "true", "yes")
        try:
            if camera:
                from core import face_auth
                frame = face_auth.capture_from_camera()
                import cv2
                from pathlib import Path
                tmp = Path(owner_gate._BIO) / f"_capture_slot{slot_i}.jpg"
                owner_gate._ensure_bio()
                cv2.imwrite(str(tmp), frame)
                path = str(tmp)
            if not path:
                return ask("owner_setup", "image_path ou camera=true?", slot=slot_i)
            info = owner_gate.register_face_slot(slot_i, path)
            return done(
                "owner_setup",
                action="enroll_face",
                slot=slot_i,
                path=info.get("path"),
                face_profile=str(info.get("enrolled_face")),
            )
        except Exception as e:
            return failed("owner_setup", f"face enroll slot {slot} failed: {e}")

    if action in ("verify", "check_owner"):
        method = str(params.get("method") or "any").lower()
        try:
            result = owner_gate.require_owner(
                method=method,
                voice_path=params.get("wav_path") or params.get("path") if method != "face" else None,
                image_path=params.get("image_path"),
                camera=str(params.get("camera") or "").lower() in ("1", "true", "yes"),
            )
            # fix voice path when method any
            if not result.get("accepted") and method in ("any", "voice"):
                vp = params.get("wav_path") or params.get("audio_path")
                if vp:
                    result = owner_gate.require_owner(method="voice", voice_path=vp)
            if result.get("accepted"):
                return done("owner_setup", action="verify", **{k: result[k] for k in result if k != "attempts"})
            return failed(
                "owner_setup",
                f"owner not verified ({result.get('detail')})",
                score=result.get("score"),
                method=result.get("method"),
            )
        except Exception as e:
            return failed("owner_setup", f"verify failed: {e}")

    if action in ("prompt", "help"):
        return done("owner_setup", action="prompt", message=owner_gate.enrollment_prompt_pt())

    return ask(
        "owner_setup",
        "o que fazer?",
        options=(
            "status | set_phrase (phrase=...) | enroll_voice (path=...) | "
            "enroll_face (slot=1|2|3, image_path=...|camera=true) | verify"
        ),
    )


    if action in ("store_key", "set_key", "vault"):
        key_name = str(params.get("key") or params.get("name") or "gemini_api_key").strip()
        value = str(params.get("value") or params.get("secret") or "").strip()
        if not value:
            return ask("owner_setup", "value da chave?", key=key_name)
        try:
            from core.secrets import store_secret, migrate_plain_secrets
            backend = store_secret(key_name, value)
            migrate_plain_secrets()
            return done("owner_setup", action="store_key", key=key_name, backend=backend)
        except Exception as e:
            return failed("owner_setup", str(e), action="store_key")


TOOL = {
    "name": "owner_setup",
    "description": (
        "Cadastro do dono na primeira inicialização e verificação biométrica. "
        "Gera memory/biometrics/vozdono.mp3, fotobase1.jpg (frente), "
        "fotobase2.jpg (lado), fotobase3.jpg (outro lado) e a frase de comando "
        "(ex: 'ok jarvis', 'acorda jarvis'). "
        "Actions: status, set_phrase, enroll_voice, enroll_face, verify. "
        "Ações críticas (shutdown/restart/reset) exigem verify por voz OU câmera."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | set_phrase | enroll_voice | enroll_face | verify | prompt",
            },
            "phrase": {"type": "STRING", "description": "Comando do dono, ex: ok jarvis"},
            "path": {"type": "STRING", "description": "Caminho de áudio ou imagem"},
            "wav_path": {"type": "STRING", "description": "Áudio para voz"},
            "image_path": {"type": "STRING", "description": "Foto para face"},
            "slot": {"type": "NUMBER", "description": "1=frente 2=ladoA 3=ladoB"},
            "camera": {"type": "STRING", "description": "true para capturar webcam"},
            "method": {"type": "STRING", "description": "voice | face | any (verify)"},
        },
        "required": [],
    },
    "handler": owner_setup,
    "tier": "core",
    "risk": "review",
}
