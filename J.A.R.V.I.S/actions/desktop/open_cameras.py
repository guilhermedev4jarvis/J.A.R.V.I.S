r"""
JARVIS action — open house cameras via VSM/VMS.exe with guided UI flow.

Flow requested by owner:
  1) Launch VSM/VSM.exe (or VMS.exe) from the project folder / configured path
  2) Screenshot → accept Windows/app permission dialog if present
  3) Screenshot → if login/password UI appears, press Enter
  4) Screenshot → open/click "Monitorar"

Relies on pyautogui + optional OCR (pytesseract). Best-effort: never crashes JARVIS.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from core import outcome

# ── resolve executable ──────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../J.A.R.V.I.S


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _candidate_exes() -> list[Path]:
    """Ordered list of possible VSM/VMS executables."""
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | str | None) -> None:
        if not p:
            return
        path = Path(p)
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(path)

    # Explicit env wins
    for k in ("VMS_APP_PATH", "ICSEE_APP_PATH", "CAMERA_APP_PATH", "VSM_APP_PATH"):
        add(_env(k))

    # User said: folder VSM/VSM.exe next to the project
    for base in (
        _PROJECT_ROOT,
        _PROJECT_ROOT.parent,
        Path.cwd(),
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ):
        add(base / "VSM" / "VSM.exe")
        add(base / "VSM" / "VMS.exe")
        add(base / "VMS" / "VMS.exe")
        add(base / "VMS" / "VSM.exe")
        add(base / "VSM.exe")
        add(base / "VMS.exe")

    # Common install dirs
    local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    for root in filter(None, [local, pf, pf86, Path(r"C:\VMS"), Path(r"C:\VSM")]):
        add(root / "VMS" / "VMS.exe")
        add(root / "VSM" / "VSM.exe")
        add(root / "VMS.exe")
        add(root / "VSM.exe")

    return out


def _find_exe() -> Optional[Path]:
    for p in _candidate_exes():
        try:
            if p.is_file():
                return p
        except Exception:
            continue
    # bare name on PATH
    for name in ("VSM.exe", "VMS.exe", "VSM", "VMS"):
        from shutil import which
        w = which(name)
        if w:
            return Path(w)
    return None


# ── screen helpers ──────────────────────────────────────────────────────────

def _shot_dir() -> Path:
    d = _PROJECT_ROOT / "memory" / "vms_launch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _screenshot(tag: str) -> Optional[Path]:
    try:
        import mss
        import mss.tools
        path = _shot_dir() / f"{int(time.time())}_{tag}.png"
        with mss.mss() as sct:
            mon = sct.monitors[0]
            shot = sct.grab(mon)
            mss.tools.to_png(shot.rgb, shot.size, output=str(path))
        return path
    except Exception:
        try:
            import pyautogui
            path = _shot_dir() / f"{int(time.time())}_{tag}.png"
            pyautogui.screenshot(str(path))
            return path
        except Exception:
            return None


def _ocr_text(img_path: Optional[Path]) -> str:
    if not img_path or not img_path.is_file():
        return ""
    # 1) tesseract
    try:
        import pytesseract
        from PIL import Image
        return (pytesseract.image_to_string(Image.open(img_path), lang="por+eng") or "").strip()
    except Exception:
        pass
    # 2) lightweight: empty — Gemini OCR is async/heavy; skip in launch path
    return ""


def _ocr_boxes(img_path: Optional[Path]) -> list[dict[str, Any]]:
    """Return list of {text,x,y,w,h} from tesseract if available."""
    if not img_path or not img_path.is_file():
        return []
    try:
        import pytesseract
        from PIL import Image
        data = pytesseract.image_to_data(Image.open(img_path), lang="por+eng", output_type=pytesseract.Output.DICT)
        boxes = []
        n = len(data.get("text") or [])
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1
            if conf >= 0 and conf < 40:
                continue
            boxes.append({
                "text": txt,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
            })
        return boxes
    except Exception:
        return []


def _click_xy(x: int, y: int) -> bool:
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.moveTo(x, y, duration=0.15)
        pyautogui.click()
        return True
    except Exception:
        return False


def _press(*keys: str) -> bool:
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def _click_text(img_path: Optional[Path], *needles: str) -> bool:
    """Click center of a word matching any needle (case-insensitive)."""
    needles_l = [n.casefold() for n in needles if n]
    boxes = _ocr_boxes(img_path)
    # also try multi-word: join nearby tokens — simple single-token match first
    for b in boxes:
        t = b["text"].casefold()
        for n in needles_l:
            if n in t or t in n:
                cx = b["x"] + b["w"] // 2
                cy = b["y"] + b["h"] // 2
                return _click_xy(cx, cy)
    # phrase: consecutive boxes
    texts = [b["text"] for b in boxes]
    for i in range(len(boxes)):
        for length in range(1, 4):
            if i + length > len(boxes):
                break
            phrase = " ".join(texts[i:i + length]).casefold()
            for n in needles_l:
                if n in phrase:
                    xs = [boxes[j]["x"] for j in range(i, i + length)]
                    ys = [boxes[j]["y"] for j in range(i, i + length)]
                    ws = [boxes[j]["w"] for j in range(i, i + length)]
                    hs = [boxes[j]["h"] for j in range(i, i + length)]
                    cx = min(xs) + (max(x + w for x, w in zip(xs, ws)) - min(xs)) // 2
                    cy = min(ys) + max(hs) // 2
                    return _click_xy(cx, cy)
    return False


def _focus_window(*title_bits: str) -> bool:
    try:
        import pygetwindow as gw
        wins = gw.getAllWindows()
        bits = [b.casefold() for b in title_bits if b]
        for w in wins:
            title = (w.title or "").casefold()
            if any(b in title for b in bits):
                try:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    # Alt-Tab once as weak fallback
    _press("alt", "tab")
    return False


# ── permission / login / monitor steps ──────────────────────────────────────

_PERMIT_WORDS = (
    "permitir", "allow", "sim", "yes", "aceitar", "ok", "abrir", "executar",
    "run", "run anyway", "mais informações", "more info", "continuar",
)
_LOGIN_WORDS = (
    "senha", "password", "usuário", "usuario", "user", "login", "entrar",
    "sign in", "account", "conta",
)
_MONITOR_WORDS = (
    "monitorar", "monitor", "live", "ao vivo", "preview", "visualizar",
    "live view", "dispositivo", "devices",
)


def _accept_permission(img: Optional[Path]) -> str:
    """Try to accept SmartScreen / app permission dialogs."""
    if _click_text(img, *_PERMIT_WORDS):
        return "clicked_permit_ocr"
    # keyboard heuristics for UAC / SmartScreen style dialogs
    # Note: real UAC (secure desktop) cannot be automated without elevation.
    time.sleep(0.3)
    if _press("left") and _press("enter"):
        pass
    time.sleep(0.2)
    _press("y")  # Yes on some English dialogs with focus
    time.sleep(0.2)
    _press("enter")
    # Alt+A / Alt+Y common accelerators
    _press("alt", "y")
    time.sleep(0.15)
    _press("alt", "a")
    return "keyboard_permit_attempt"


def _handle_login(img: Optional[Path]) -> str:
    text = _ocr_text(img).casefold()
    if any(w in text for w in _LOGIN_WORDS) or _click_text(img, "entrar", "login", "ok"):
        # credentials already saved → Enter
        time.sleep(0.2)
        _press("enter")
        time.sleep(0.4)
        _press("enter")
        return "enter_on_login"
    # still press enter once — many clients auto-fill and wait for Enter
    _press("enter")
    return "enter_fallback"


def _open_monitor(img: Optional[Path]) -> str:
    if _click_text(img, *_MONITOR_WORDS):
        return "clicked_monitor_ocr"
    # try a few tab+enter cycles to reach primary action
    for _ in range(4):
        _press("tab")
        time.sleep(0.12)
    _press("enter")
    # double-click center-ish of screen as last resort for big "Monitorar" tiles
    try:
        import pyautogui
        sw, sh = pyautogui.size()
        # center-left tile often used by VMS home
        for frac in ((0.35, 0.45), (0.5, 0.45), (0.35, 0.55)):
            pyautogui.click(int(sw * frac[0]), int(sh * frac[1]))
            time.sleep(0.25)
    except Exception:
        pass
    return "monitor_heuristic"


def _launch(exe: Path) -> dict:
    try:
        # no shell — start process from its directory so DLLs resolve
        kwargs = {
            "cwd": str(exe.parent),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        proc = subprocess.Popen([str(exe)], **kwargs)
        return {"ok": True, "pid": proc.pid, "exe": str(exe)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "exe": str(exe)}


def open_cameras(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    skip_ui = bool(parameters.get("skip_ui") or parameters.get("only_launch"))

    exe = _find_exe()
    if not exe:
        return outcome.failed(
            "open_cameras",
            error=(
                "VSM.exe/VMS.exe nao encontrado. Coloque em J.A.R.V.I.S\\VSM/VSM.exe "
                "ou defina VMS_APP_PATH / VSM_APP_PATH no .env"
            ),
        )

    launched = _launch(exe)
    if not launched.get("ok"):
        return outcome.failed("open_cameras", error=launched.get("error") or "launch_failed", exe=str(exe))

    steps: list[str] = [f"launched:{exe.name}"]
    shots: list[str] = []

    if skip_ui:
        return outcome.done(
            "open_cameras",
            action="launch_only",
            app=str(exe),
            pid=launched.get("pid"),
            steps=steps,
        )

    # Wait for first window
    time.sleep(2.5)
    _focus_window("VSM", "VMS", "iCSee", "VMS Pro", exe.stem)
    time.sleep(0.5)

    # Step 1 — permission
    s1 = _screenshot("01_permission")
    if s1:
        shots.append(str(s1))
    steps.append("permission:" + _accept_permission(s1))
    time.sleep(1.8)

    # Step 2 — login
    _focus_window("VSM", "VMS", "iCSee", exe.stem)
    s2 = _screenshot("02_login")
    if s2:
        shots.append(str(s2))
    steps.append("login:" + _handle_login(s2))
    time.sleep(2.0)

    # Step 3 — Monitorar
    _focus_window("VSM", "VMS", "iCSee", exe.stem)
    s3 = _screenshot("03_home")
    if s3:
        shots.append(str(s3))
    steps.append("monitor:" + _open_monitor(s3))
    time.sleep(1.2)

    # Final shot for audit
    s4 = _screenshot("04_done")
    if s4:
        shots.append(str(s4))

    return outcome.done(
        "open_cameras",
        action="launch_and_ui",
        app=str(exe),
        pid=launched.get("pid"),
        steps=" | ".join(steps),
        screenshots=len(shots),
        shot_dir=str(_shot_dir()),
        message=f"VSM/VMS iniciado ({exe.name}); permissao/login/Monitorar tentados.",
    )


TOOL = {
    "name": "open_cameras",
    "description": (
        "Abre o cliente de cameras da casa: executa VSM\\\\VSM.exe (ou VMS.exe), "
        "aceita o dialogo de permissao (print + clicar Permitir/Sim), "
        "se aparecer login/senha da Enter, depois abre Monitorar. "
        "USE SEMPRE que o usuario pedir: abrir cameras, ver cameras, mostrar "
        "cameras, abrir VSM/VMS/iCSee, CFTV, monitoramento, cameras da casa. "
        "Nao use open_app nem a webcam do notebook para isso."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "skip_ui": {
                "type": "BOOLEAN",
                "description": "Se true, so lanca o exe sem clicar na UI.",
            },
            "reason": {
                "type": "STRING",
                "description": "Motivo opcional do pedido.",
            },
        },
        "required": [],
    },
    "handler": open_cameras,
    "tier": "core",
    "risk": "safe",
}
