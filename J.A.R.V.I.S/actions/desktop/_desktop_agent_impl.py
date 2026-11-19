"""
Plugin: desktop_agent v5.1

Fecha lacunas da v4 + loop Observar → Agir → Validar (GUI grounding):
  • Web: quando o objetivo é browser, tenta Playwright (browser_control) antes de pixels
  • DPI: GetDpiForMonitor + mapeamento físico explícito
  • Interferência do usuário: detecta mouse/foco externo → pausa e re-foca sticky
  • Economia Gemini: modo economy, imagens menores, skip de visão com cache/heurística
  • OCR: pytesseract se houver; senão só Gemini (sem depender de binário)
  • Lock: PID vivo + heartbeat + atexit; lock morto é roubado
  • Fila: se já há missão, enfileira em vez de só rejeitar (opcional queue=true)
  • Auditoria: log append-only de cada ação em memory/desktop_missions/audit.log
  • Compliance: risk tags no plano + confirm_steps / require_confirm_risky
  • Validate: phash antes/depois + checagem rápida; validate_fail → replan

pip recomendado:
  pywinauto uiautomation pygetwindow mss opencv-python-headless pillow playwright
  pytesseract  # opcional
"""
from __future__ import annotations

import atexit
import hashlib
import io
import json
import os
import re
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_DEPS: dict[str, bool] = {}

def _probe_deps() -> dict:
    global _DEPS
    _DEPS = {}
    for name, mod in (
        ("mss", "mss"), ("cv2", "cv2"), ("pywinauto", "pywinauto"),
        ("uiautomation", "uiautomation"), ("pygetwindow", "pygetwindow"),
        ("pytesseract", "pytesseract"), ("PIL", "PIL"), ("playwright", "playwright"),
    ):
        try:
            __import__(mod)
            _DEPS[name] = True
        except Exception:
            _DEPS[name] = False
    return _DEPS

_FORBIDDEN = re.compile(
    r"\b(shutdown|reinici|restart|format|rm\s+-rf|del\s+/s|deslig|apaga(r)?\s+tudo|"
    r"excluir\s+tudo|wipe|toggle_wifi|desconect(ar)?\s+wifi)\b", re.I,
)
_BLOCKER = re.compile(
    r"\b(captcha|recaptcha|hcaptcha|cloudflare|2fa|two[\s-]?factor|"
    r"verifica(ção|cao) em duas etapas|otp|authenticator|sign in|log in|login|"
    r"faça login|password|senha|verify you are human|não sou um robô)\b", re.I,
)
_LOADING = re.compile(
    r"\b(loading|carregando|please wait|aguarde|spinner|skeleton|conectando)\b", re.I,
)
_WEB_GOAL = re.compile(
    r"\b(chrome|firefox|edge|browser|navegador|site|url|http|www\.|gmail|youtube|"
    r"google|notion|figma|github|stackoverflow|pesquisa(r)? na web|abre o site)\b", re.I,
)
_VAGUE = re.compile(r"^(organiza|melhorar?|arruma|limpa|faz|ajuda|resolve)\b", re.I)

_MAX_STEPS = 25
_DEFAULT_STEPS = 12
_APP_WAIT = {
    "chrome": 40, "google chrome": 40, "firefox": 35, "edge": 35,
    "code": 50, "visual studio code": 55, "spotify": 28, "excel": 45,
    "word": 40, "outlook": 45, "teams": 50, "figma": 45, "notion": 40,
    "notepad": 12, "calc": 10, "calculator": 10, "explorer": 15,
}
_MISSION = "desktop_missions"
_LOCK = "desktop_agent.lock"
_QUEUE = "mission_queue.jsonl"
_AUDIT = "audit.log"

# interference tracking
_last_mouse: Optional[tuple[int, int]] = None
_our_click_until = 0.0


def _log(msg: str, player=None) -> None:
    print(f"[DesktopAgent] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _mem() -> Path:
    try:
        from memory.memory_manager import get_base_dir
        p = get_base_dir() / "memory" / _MISSION
    except Exception:
        p = Path.home() / ".jarvis" / _MISSION
    p.mkdir(parents=True, exist_ok=True)
    return p


def _backup() -> Path:
    p = Path.home() / "Documents" / "JarvisMissions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _audit(line: str) -> None:
    try:
        with (_mem() / _AUDIT).open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except Exception:
        pass


# ── Lock with live PID ───────────────────────────────────────────────────────

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            k.CloseHandle(h)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _acquire_lock() -> bool:
    path = _mem() / _LOCK
    now = time.time()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            ts = float(data.get("ts") or 0)
            if _pid_alive(pid) and now - ts < 900:
                return False
            # dead or stale → steal
        except Exception:
            pass
    path.write_text(json.dumps({"ts": now, "pid": os.getpid(), "hb": now}), encoding="utf-8")
    return True


def _heartbeat_lock() -> None:
    path = _mem() / _LOCK
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "pid": os.getpid(), "hb": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _release_lock() -> None:
    path = _mem() / _LOCK
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                path.unlink(missing_ok=True)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


atexit.register(_release_lock)


def _enqueue(payload: dict) -> str:
    path = _mem() / _QUEUE
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return f"Missão enfileirada. Quando a atual terminar, peça 'processa fila desktop' ou rode de novo."


# ── Mission I/O ──────────────────────────────────────────────────────────────

def _save_mission(state: dict) -> str:
    mid = state.get("id") or datetime.now().strftime("%Y%m%d_%H%M%S")
    state["id"] = mid
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    raw = json.dumps(state, ensure_ascii=False, indent=2)
    (_mem() / f"{mid}.json").write_text(raw, encoding="utf-8")
    (_mem() / "latest.json").write_text(json.dumps({"id": mid}), encoding="utf-8")
    try:
        (_backup() / f"{mid}.json").write_text(raw, encoding="utf-8")
    except Exception:
        pass
    return mid


def _load_mission(mission_id: Optional[str] = None) -> Optional[dict]:
    d = _mem()
    if not mission_id:
        latest = d / "latest.json"
        if latest.exists():
            try:
                mission_id = json.loads(latest.read_text(encoding="utf-8")).get("id")
            except Exception:
                mission_id = None
    if not mission_id:
        files = sorted(
            [f for f in d.glob("*.json") if f.name not in (_LOCK, "latest.json") and not f.name.endswith(".jsonl")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not files:
            b = sorted(_backup().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            return json.loads(b[0].read_text(encoding="utf-8")) if b else None
        mission_id = files[0].stem
    for path in (d / f"{mission_id}.json", _backup() / f"{mission_id}.json"):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


# ── Monitors + DPI ───────────────────────────────────────────────────────────

@dataclass
class MonitorInfo:
    index: int
    left: int
    top: int
    width: int
    height: int
    dpi: float = 96.0

    @property
    def scale(self) -> float:
        return self.dpi / 96.0


def _monitor_dpi(left: int, top: int) -> float:
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore
        mon = user32.MonitorFromPoint(wintypes.POINT(int(left) + 10, int(top) + 10), 2)
        x = ctypes.c_uint()
        y = ctypes.c_uint()
        shcore.GetDpiForMonitor(mon, 0, ctypes.byref(x), ctypes.byref(y))
        return float(x.value or 96)
    except Exception:
        try:
            import ctypes
            return float(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            return 96.0


def _list_monitors() -> list[MonitorInfo]:
    out: list[MonitorInfo] = []
    try:
        import mss
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    continue
                left, top = int(m["left"]), int(m["top"])
                out.append(MonitorInfo(
                    i, left, top, int(m["width"]), int(m["height"]),
                    dpi=_monitor_dpi(left, top),
                ))
    except Exception as e:
        print(f"[DesktopAgent] mss: {e}")
    if not out:
        try:
            import pyautogui
            w, h = pyautogui.size()
            out = [MonitorInfo(1, 0, 0, w, h, _monitor_dpi(0, 0))]
        except Exception:
            out = [MonitorInfo(1, 0, 0, 1920, 1080, 96.0)]
    return out


def _pick_monitor(pref: int) -> MonitorInfo:
    mons = _list_monitors()
    if pref <= 0:
        left = min(m.left for m in mons)
        top = min(m.top for m in mons)
        right = max(m.left + m.width for m in mons)
        bottom = max(m.top + m.height for m in mons)
        return MonitorInfo(0, left, top, right - left, bottom - top, mons[0].dpi)
    for m in mons:
        if m.index == pref:
            return m
    return mons[0]


@dataclass
class Shot:
    data: bytes
    mon: MonitorInfo
    img_w: int
    img_h: int
    phash: str
    full_w: int
    full_h: int


def _capture(mon: MonitorInfo, max_side: int = 1600, economy: bool = False) -> Shot:
    from PIL import Image
    if economy:
        max_side = min(max_side, 1024)
    try:
        import mss
        with mss.mss() as sct:
            region = (
                sct.monitors[mon.index] if mon.index > 0 else
                {"left": mon.left, "top": mon.top, "width": mon.width, "height": mon.height}
            )
            raw = sct.grab(region)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
    except Exception:
        import pyautogui
        img = pyautogui.screenshot()
        mon = MonitorInfo(1, 0, 0, img.size[0], img.size[1], _monitor_dpi(0, 0))

    full_w, full_h = img.size
    phash = hashlib.md5(img.convert("L").resize((32, 32)).tobytes()).hexdigest()
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=62 if economy else 78)
    return Shot(buf.getvalue(), mon, img.size[0], img.size[1], phash, full_w, full_h)


def _wait_settle(mon: MonitorInfo, need: int = 2, timeout: float = 3.5, economy: bool = False) -> Shot:
    deadline = time.monotonic() + timeout
    last = None
    stable = 0
    shot = _capture(mon, economy=economy)
    while time.monotonic() < deadline:
        time.sleep(0.28)
        nxt = _capture(mon, economy=economy)
        if last and nxt.phash == last.phash:
            stable += 1
            shot = nxt
            if stable >= need:
                return shot
        else:
            stable = 0
            last = nxt
            shot = nxt
    return shot


def _map_to_global(lx: int, ly: int, shot: Shot) -> tuple[int, int]:
    # mss region is already physical pixels; only undo thumbnail
    sx = shot.full_w / max(shot.img_w, 1)
    sy = shot.full_h / max(shot.img_h, 1)
    gx = int(shot.mon.left + lx * sx)
    gy = int(shot.mon.top + ly * sy)
    gx = max(shot.mon.left, min(shot.mon.left + shot.mon.width - 1, gx))
    gy = max(shot.mon.top, min(shot.mon.top + shot.mon.height - 1, gy))
    return gx, gy


# ── Interference ─────────────────────────────────────────────────────────────

def _mouse_pos() -> tuple[int, int]:
    try:
        import pyautogui
        p = pyautogui.position()
        return int(p.x), int(p.y)
    except Exception:
        return (0, 0)


def _mark_our_input() -> None:
    global _our_click_until, _last_mouse
    _our_click_until = time.monotonic() + 1.2
    _last_mouse = _mouse_pos()


def _user_interfered(sticky: str) -> Optional[str]:
    """Return reason if user seems to have taken over."""
    global _last_mouse
    if time.monotonic() < _our_click_until:
        _last_mouse = _mouse_pos()
        return None
    pos = _mouse_pos()
    if _last_mouse is not None:
        dx = abs(pos[0] - _last_mouse[0])
        dy = abs(pos[1] - _last_mouse[1])
        if dx > 80 or dy > 80:
            _last_mouse = pos
            return f"mouse moved by user (Δ{dx},{dy})"
    _last_mouse = pos
    if sticky:
        try:
            import pyautogui
            aw = pyautogui.getActiveWindow()
            title = (aw.title if aw else "") or ""
            if sticky.lower() not in title.lower():
                return f"focus left sticky window (now: {title[:60] or 'none'})"
        except Exception:
            pass
    return None


# ── Vision / UIA / OCR ───────────────────────────────────────────────────────

def _ocr_local(shot: Shot) -> str:
    if not _DEPS.get("pytesseract"):
        return ""
    try:
        import pytesseract
        from PIL import Image
        return (pytesseract.image_to_string(Image.open(io.BytesIO(shot.data)), lang="por+eng") or "")[:1500]
    except Exception:
        return ""


def _vision_xy(description: str, shot: Shot, economy: bool = False) -> Optional[tuple[int, int]]:
    from core import gemini
    from google.genai import types as gtypes
    ocr = "" if economy else _ocr_local(shot)
    ocr_bit = f"\nOCR:\n{ocr[:600]}" if ocr else ""
    prompt = (
        f"Image {shot.img_w}x{shot.img_h}. Find '{description}'. "
        f"Accept PT/EN synonyms (Search/Pesquisar, Send/Enviar, Settings/Configurações). "
        f"{ocr_bit}\nReply ONLY x,y in THIS image or NOT_FOUND."
    )
    try:
        resp = gemini.call(
            [gtypes.Part.from_bytes(data=shot.data, mime_type="image/jpeg"), prompt],
            tier=gemini.FAST, timeout_ms=22_000 if economy else 28_000,
        )
        if resp is None:
            return None
        text = (getattr(resp, "text", None) or "").strip()
        if "NOT_FOUND" in text.upper():
            return None
        m = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if not m:
            return None
        return _map_to_global(int(m.group(1)), int(m.group(2)), shot)
    except Exception as e:
        print(f"[DesktopAgent] vision: {e}")
        return None


def _zoom_relocate(description: str, mon: MonitorInfo, cx: int, cy: int, box: int = 220) -> Optional[tuple[int, int]]:
    from PIL import Image
    from core import gemini
    from google.genai import types as gtypes
    try:
        import mss
        with mss.mss() as sct:
            left = max(mon.left, cx - box // 2)
            top = max(mon.top, cy - box // 2)
            width = min(box, mon.left + mon.width - left)
            height = min(box, mon.top + mon.height - top)
            raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
            img = Image.frombytes("RGB", raw.size, raw.rgb)
    except Exception:
        return None
    img = img.resize((img.size[0] * 2, img.size[1] * 2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    try:
        resp = gemini.call(
            [gtypes.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
             f"Zoomed crop. Find '{description}' (PT/EN). ONLY x,y or NOT_FOUND."],
            tier=gemini.FAST, timeout_ms=22_000,
        )
        text = (getattr(resp, "text", None) or "").strip()
        if not text or "NOT_FOUND" in text.upper():
            return None
        m = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if not m:
            return None
        return int(left + int(m.group(1)) / 2), int(top + int(m.group(2)) / 2)
    except Exception:
        return None


def _uia_click(name: str) -> Optional[str]:
    if _DEPS.get("uiautomation"):
        try:
            import uiautomation as auto  # type: ignore
            ctrl = auto.Control(searchDepth=8, Name=name)
            if ctrl.Exists(0.4):
                ctrl.Click()
                return f"uiautomation clicked '{name}'"
            root = auto.GetRootControl()
            for c, _d in auto.WalkControl(root, maxDepth=6):
                try:
                    n = c.Name or ""
                    if name.lower() in n.lower() and c.IsEnabled:
                        c.Click()
                        return f"uiautomation clicked '{n[:50]}'"
                except Exception:
                    continue
        except Exception as e:
            print(f"[DesktopAgent] uia: {e}")
    if _DEPS.get("pywinauto"):
        try:
            from pywinauto import Desktop  # type: ignore
            desk = Desktop(backend="uia")
            for w in desk.windows():
                try:
                    if not w.is_visible():
                        continue
                    ctrl = w.child_window(title_re=f".*{re.escape(name)}.*")
                    if ctrl.exists(timeout=0.35):
                        ctrl.click_input()
                        return f"pywinauto clicked '{name}'"
                except Exception:
                    continue
        except Exception:
            pass
    return None


def _click_reliable(description: str, mon: MonitorInfo, double: bool = False, economy: bool = False) -> str:
    uia = _uia_click(description)
    if uia and "clicked" in uia.lower():
        _mark_our_input()
        return uia
    shot1 = _wait_settle(mon, need=2 if not economy else 1, timeout=3.0, economy=economy)
    c1 = _vision_xy(description, shot1, economy=economy)
    if not c1:
        for m in _list_monitors():
            if m.index == mon.index:
                continue
            s = _wait_settle(m, need=1, timeout=1.8, economy=economy)
            c1 = _vision_xy(description, s, economy=economy)
            if c1:
                mon = m
                break
    if not c1:
        return f"Element not found: {description}"
    gx, gy = c1
    if not economy:
        refined = _zoom_relocate(description, mon, gx, gy)
        if refined:
            gx, gy = refined
        time.sleep(0.15)
        shot2 = _wait_settle(mon, need=1, timeout=1.8, economy=economy)
        c2 = _vision_xy(description, shot2, economy=economy)
        if c2 and abs(c2[0] - gx) <= 50 and abs(c2[1] - gy) <= 50:
            gx, gy = (gx + c2[0]) // 2, (gy + c2[1]) // 2
    import actions.system._computer_control_impl as cc
    _mark_our_input()
    return cc._click(gx, gy, clicks=2 if double else 1)


# ── Observe ──────────────────────────────────────────────────────────────────

_last_hash: Optional[str] = None
_last_obs = ""


def _observe(goal: str, mon: MonitorInfo, last_action: str, last_result: str,
             force: bool = False, economy: bool = False) -> str:
    global _last_hash, _last_obs
    from core import gemini
    from google.genai import types as gtypes
    shot = _capture(mon, economy=economy)
    if not force and _last_hash == shot.phash and _last_obs:
        return _last_obs
    try:
        prompt = (
            f"Desktop {shot.img_w}x{shot.img_h}. Goal:{goal}\n"
            f"Last:{last_action or '-'}→{last_result or '-'}\n"
            "3-5 short PT bullets. BLOCKER: if captcha/2fa/login. LOADING: yes if spinner."
        )
        text = gemini.text(
            [gtypes.Part.from_bytes(data=shot.data, mime_type="image/jpeg"), prompt],
            tier=gemini.FAST, timeout_ms=18_000 if economy else 22_000, default="",
        ) or "(sem descrição)"
        _last_hash, _last_obs = shot.phash, text
        return text
    except Exception as e:
        return f"(observe fail: {e})"


def _detect_blocker(obs: str) -> Optional[str]:
    if not obs:
        return None
    for line in obs.splitlines():
        if "BLOCKER" in line.upper():
            return line.strip()
    if _BLOCKER.search(obs):
        return f"Barreira humana: {_BLOCKER.search(obs).group(0)}"
    return None


def _is_loading(obs: str) -> bool:
    return bool(obs and (_LOADING.search(obs) or "LOADING: yes" in obs.upper()))


def _adaptive_wait(mon, goal, economy, max_total=40.0) -> str:
    waited = 0.0
    delay = 1.5
    while waited < max_total:
        obs = _observe(goal, mon, "wait_ready", f"{waited:.0f}s", force=True, economy=economy)
        if _detect_blocker(obs):
            return f"blocker: {_detect_blocker(obs)}"
        if not _is_loading(obs):
            return f"ready after {waited:.0f}s"
        time.sleep(delay)
        waited += delay
        delay = min(delay * 1.5, 7.0)
    return f"still loading after {waited:.0f}s"


# ── Focus / windows ──────────────────────────────────────────────────────────

def _window_titles() -> list[str]:
    titles = []
    if _DEPS.get("pygetwindow"):
        try:
            import pygetwindow as gw  # type: ignore
            for t in gw.getAllTitles():
                if t and t.strip():
                    titles.append(t.strip())
        except Exception:
            pass
    return titles


def _focus_window_strong(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return "focus: empty"
    if _DEPS.get("pygetwindow"):
        try:
            import pygetwindow as gw  # type: ignore
            matches = [w for w in gw.getAllWindows() if title.lower() in (w.title or "").lower()]
            if matches:
                w = matches[0]
                try:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    time.sleep(0.2)
                    return f"Focused '{w.title[:70]}'"
                except Exception:
                    pass
        except Exception:
            pass
    try:
        from actions.system._computer_control_impl import _focus_window
        return _focus_window(title)
    except Exception as e:
        return f"focus failed: {e}"


def _ensure_sticky(sticky: str) -> None:
    if not sticky:
        return
    try:
        import pyautogui
        aw = pyautogui.getActiveWindow()
        title = (aw.title if aw else "") or ""
    except Exception:
        title = ""
    if sticky.lower() not in title.lower():
        _focus_window_strong(sticky)


def _wait_for_app(name: str, timeout: Optional[float] = None) -> str:
    needle = (name or "").strip().lower()
    timeout = float(timeout or _APP_WAIT.get(needle, 28.0))
    aliases = {
        "notepad": ["notepad", "bloco de notas"], "chrome": ["chrome", "google chrome"],
        "firefox": ["firefox"], "edge": ["edge", "microsoft edge"],
        "code": ["visual studio code", "code"], "spotify": ["spotify"],
        "explorer": ["file explorer", "explorador"], "calc": ["calculator", "calculadora"],
    }
    keys = list({*aliases.get(needle, [needle]), needle})
    deadline = time.monotonic() + timeout
    last: list[str] = []
    while time.monotonic() < deadline:
        last = _window_titles()
        for t in last:
            if any(k in t.lower() for k in keys):
                time.sleep(0.25)
                return f"App ready: '{t}'"
        time.sleep(0.4)
    return f"Timeout waiting for '{name}' ({timeout:.0f}s). Visible: {', '.join(last[:5]) or 'none'}"


def _scroll_until(description: str, mon: MonitorInfo, direction="down", max_scrolls=12, economy=False) -> str:
    import actions.system._computer_control_impl as cc
    for i in range(max_scrolls):
        shot = _wait_settle(mon, need=1, timeout=1.0, economy=economy)
        if _vision_xy(description, shot, economy=economy):
            return f"Found after {i} scroll(s): {description}"
        cc._scroll(direction, amount=4)
        time.sleep(0.3)
    return f"scroll_until gave up: {description}"


# ── Playwright / browser_control path ────────────────────────────────────────

def _browser_action(action: str, **kwargs) -> str:
    """Delegate to project's browser_control action when available."""
    try:
        import actions.web_media.browser_control as bc
        params = {"action": action, **kwargs}
        return str(bc(params))
    except Exception as e:
        return f"browser_control unavailable: {e}"


def _goal_is_web(goal: str) -> bool:
    return bool(_WEB_GOAL.search(goal or ""))


# ── Plan ─────────────────────────────────────────────────────────────────────

def _goal_too_vague(goal: str) -> bool:
    g = goal.strip()
    return len(g) < 12 or (bool(_VAGUE.match(g)) and len(g) < 45)


def _build_plan(goal: str, observation: str, max_steps: int, prefer_browser: bool) -> list[dict]:
    from core import gemini
    wave = min(max_steps, 10)
    browser_hint = ""
    if prefer_browser and _goal_is_web(goal):
        browser_hint = (
            "Prefer browser_* actions when interacting with web pages: "
            "browser_goto, browser_click_text, browser_type, browser_press, browser_get_text. "
            "Use pixel click_desc only if browser_* is insufficient.\n"
        )
    prompt = f"""Desktop planner. GOAL: {goal}
SCREEN: {observation}
{browser_hint}
JSON array ≤{wave} steps. Actions:
open_app,focus_window,hotkey,press,type,smart_type,click_desc,double_click_desc,drag,scroll,scroll_until,wait,wait_for_app,wait_for_screen,wait_ready,uia_click,browser_goto,browser_click_text,browser_type,browser_press,browser_get_text,done
Each: {{"action":"...","args":{{}},"why":"...","risk":"low|medium|high"}}
Rules: open_app→wait_for_app; web loads→wait_ready; long lists→scroll_until; PT/EN ok; CAPTCHA→done; never shutdown/wipe/wifi.
ONLY JSON array."""
    data = gemini.as_json(prompt, tier=gemini.SMART, timeout_ms=50_000, default=None)
    if isinstance(data, dict):
        data = data.get("steps") or data.get("plan") or []
    if not isinstance(data, list):
        return [
            {"action": "open_app", "args": {"name": "notepad"}, "why": "fallback", "risk": "low"},
            {"action": "wait_for_app", "args": {"name": "notepad"}, "why": "wait", "risk": "low"},
        ]
    out = []
    for item in data[:wave]:
        if isinstance(item, dict) and item.get("action"):
            out.append({
                "action": str(item["action"]).strip(),
                "args": item["args"] if isinstance(item.get("args"), dict) else {},
                "why": str(item.get("why") or "")[:140],
                "risk": str(item.get("risk") or "low"),
            })
    return out


def _replan(goal, observation, failed_step, failed_result, budget, done_so_far):
    from core import gemini
    data = gemini.as_json(
        f"FAILED step. GOAL:{goal}\nSCREEN:{observation}\nFAILED:{failed_step}→{failed_result}\n"
        f"DONE:{done_so_far[-8:]}\nJSON array ≤{budget} steps. ONLY JSON.",
        tier=gemini.SMART, timeout_ms=40_000, default=None,
    )
    if isinstance(data, dict):
        data = data.get("steps") or []
    if not isinstance(data, list):
        return [{"action": "done", "args": {}, "why": "replan failed", "risk": "low"}]
    out = []
    for item in data[:budget]:
        if isinstance(item, dict) and item.get("action"):
            out.append({
                "action": str(item["action"]).strip(),
                "args": item["args"] if isinstance(item.get("args"), dict) else {},
                "why": str(item.get("why") or "")[:140],
                "risk": str(item.get("risk") or "low"),
            })
    return out


# ── Execute ──────────────────────────────────────────────────────────────────

def _exec_open_app(name: str) -> str:
    try:
        from .open_app import open_app as _oa
        return str(_oa({"app_name": name}))
    except Exception as e:
        print(f"[DesktopAgent] open_app: {e}")
    import platform, subprocess
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        time.sleep(0.5)
        return f"Launched '{name}'"
    except Exception as e2:
        return f"Could not open '{name}': {e2}"


def _execute(step: dict, mon: MonitorInfo, dry: bool, sticky: str, goal: str, economy: bool) -> str:
    action = (step.get("action") or "").lower().strip()
    args = step.get("args") or {}
    if action in ("done", "fail"):
        return action
    if dry:
        return f"[dry-run] {action} {args}"

    # interference check
    reason = _user_interfered(sticky)
    if reason:
        _audit(f"INTERFERENCE {reason}")
        _ensure_sticky(sticky)
        time.sleep(0.3)
        # if still wrong focus, abort step softly
        reason2 = _user_interfered(sticky)
        if reason2 and sticky:
            return f"Paused — user interference: {reason2}"

    _ensure_sticky(sticky)
    import actions.system._computer_control_impl as cc

    try:
        if action == "open_app":
            r = _exec_open_app(str(args.get("name") or args.get("app") or ""))
            _mark_our_input()
            return r
        if action == "wait_for_app":
            return _wait_for_app(str(args.get("name") or args.get("app") or ""),
                                 float(args["timeout"]) if args.get("timeout") else None)
        if action == "wait_for_screen":
            desc = str(args.get("description") or args.get("desc") or "")
            if not desc:
                return "wait_for_screen: missing description"
            deadline = time.monotonic() + float(args.get("timeout") or 20)
            while time.monotonic() < deadline:
                shot = _wait_settle(mon, need=1, timeout=1.0, economy=economy)
                if _vision_xy(desc, shot, economy=economy):
                    return f"Element visible: {desc}"
                time.sleep(0.4)
            return f"Timeout waiting for element: {desc}"
        if action == "wait_ready":
            return _adaptive_wait(mon, goal, economy, float(args.get("timeout") or 40))
        if action == "scroll_until":
            return _scroll_until(str(args.get("description") or ""), mon,
                                 str(args.get("direction") or "down"),
                                 int(args.get("max_scrolls") or 12), economy)
        if action == "focus_window":
            return _focus_window_strong(str(args.get("title") or args.get("name") or ""))
        if action == "uia_click":
            name = str(args.get("name") or args.get("description") or "")
            r = _uia_click(name)
            if r:
                _mark_our_input()
                return r
            return _click_reliable(name, mon, economy=economy)
        if action.startswith("browser_"):
            # Map to browser_control actions
            mapping = {
                "browser_goto": ("go_to", {"url": args.get("url") or args.get("text") or ""}),
                "browser_click_text": ("smart_click", {"description": args.get("description") or args.get("text") or ""}),
                "browser_type": ("smart_type", {
                    "description": args.get("description") or args.get("field") or "",
                    "text": args.get("text") or "",
                }),
                "browser_press": ("press", {"key": args.get("key") or "Enter"}),
                "browser_get_text": ("get_text", {}),
            }
            if action in mapping:
                act, kw = mapping[action]
                # browser_control uses 'action' key
                params = {"action": act, **kw}
                if args.get("browser"):
                    params["browser"] = args["browser"]
                try:
                    import actions.web_media.browser_control as bc
                    _mark_our_input()
                    return str(bc(params))
                except Exception as e:
                    return f"browser path failed ({e}); try pixel UI"
            return f"unknown browser action {action}"
        if action == "hotkey":
            keys = str(args.get("keys") or "")
            parts = [k.strip() for k in keys.replace("-", "+").split("+") if k.strip()]
            _mark_our_input()
            return cc._hotkey(*parts) if parts else "hotkey: empty"
        if action == "press":
            _mark_our_input()
            return cc._press(str(args.get("key") or "enter"))
        if action in ("type", "smart_type"):
            text = str(args.get("text") or "")
            if not text:
                return "type: empty"
            _mark_our_input()
            if action == "smart_type" or len(text) > 20:
                return cc._smart_type(text, clear_first=bool(args.get("clear_first", False)))
            return cc._type(text)
        if action in ("click_desc", "double_click_desc", "screen_click"):
            desc = str(args.get("description") or args.get("desc") or "")
            if not desc:
                return "click_desc: missing description"
            return _click_reliable(desc, mon, double=("double" in action), economy=economy)
        if action == "drag":
            a, b = str(args.get("start_desc") or ""), str(args.get("end_desc") or "")
            if not a or not b:
                return "drag: need start_desc and end_desc"
            shot = _wait_settle(mon, economy=economy)
            h1, h2 = _vision_xy(a, shot, economy), _vision_xy(b, shot, economy)
            if not h1 or not h2:
                return "drag: element not found"
            _mark_our_input()
            try:
                return cc._drag(h1[0], h1[1], h2[0], h2[1], duration=0.55)
            except Exception:
                import pyautogui
                pyautogui.moveTo(h1[0], h1[1], duration=0.15)
                pyautogui.dragTo(h2[0], h2[1], duration=0.55, button="left")
                return "drag ok"
        if action == "scroll":
            _mark_our_input()
            return cc._scroll(str(args.get("direction") or "down"), int(args.get("amount") or 3))
        if action == "wait":
            sec = max(0.2, min(float(args.get("seconds") or 1), 12.0))
            time.sleep(sec)
            return f"waited {sec:.1f}s"
        if action == "screenshot":
            return cc._screenshot(None)
        return f"Unknown action '{action}'"
    except PermissionError as e:
        return f"Permission denied: {e}"
    except Exception as e:
        err = str(e).lower()
        if "access" in err or "permission" in err:
            return f"Permission/UAC: {e}"
        return f"exec error ({action}): {e}"


def _is_failure(result: str) -> bool:
    r = (result or "").lower()
    return any(m in r for m in (
        "not found", "não encontr", "nao encontr", "timeout", "failed",
        "could not", "unknown action", "missing", "permission", "denied",
        "gave up", "interference", "unavailable",
        "validate_fail", "no_screen_change",
    ))


def _screen_fingerprint(mon: MonitorInfo, economy: bool = False) -> str:
    """Cheap visual fingerprint (Shot.phash) so we can tell if pixels moved."""
    try:
        shot = _capture(mon, max_side=640 if economy else 960, economy=economy)
        return str(getattr(shot, "phash", "") or "")
    except Exception:
        return ""


def _validate_action(
    goal: str,
    step: dict,
    mon: MonitorInfo,
    before_fp: str,
    last_result: str,
    economy: bool = False,
) -> tuple[bool, str]:
    """Observe → Act → Validate loop step.

    Returns (ok, detail). ok=False means the UI did not change as expected and
    the planner should re-observe / replan instead of trusting the click.
    """
    action = (step.get("action") or "").lower()
    # Pure waits / no-ops — nothing to validate visually
    if action in ("done", "wait", "sleep", "note"):
        return True, "noop"

    if _is_failure(last_result):
        return False, f"action reported failure: {last_result[:120]}"

    # Let the UI settle, then compare fingerprint + optional LLM check
    time.sleep(0.18 if economy else 0.28)
    after_fp = _screen_fingerprint(mon, economy=economy)
    changed = bool(before_fp and after_fp and before_fp != after_fp)

    # Clicks / typing that claim success but left the screen identical are suspicious
    visual_actions = (
        "click_desc", "double_click_desc", "uia_click", "drag", "hotkey",
        "press", "type", "scroll_until", "browser_click_text", "browser_goto",
        "browser_press", "open_app",
    )
    if action in visual_actions and before_fp and after_fp and not changed:
        # One more settle pass (slow windows)
        time.sleep(0.45 if not economy else 0.25)
        after_fp2 = _screen_fingerprint(mon, economy=economy)
        changed = bool(after_fp2 and after_fp2 != before_fp)
        if not changed:
            return False, "validate_fail: no_screen_change after action"

    # Targeted LLM check only when economy is off and the step is high-impact
    if not economy and action in ("click_desc", "double_click_desc", "uia_click", "browser_goto", "open_app"):
        try:
            from core import gemini
            obs = _observe(goal, mon, action, last_result, force=True, economy=True)
            expected = step.get("why") or step.get("args") or action
            data = gemini.as_json(
                f"Goal:{goal}\nAction:{action} expected:{expected}\n"
                f"Result:{last_result}\nScreen:{obs[:900]}\n"
                f'JSON {{"ok":true/false,"reason":"short PT"}}',
                tier=gemini.FAST, timeout_ms=12_000, default=None,
            )
            if isinstance(data, dict) and data.get("ok") is False:
                return False, f"validate_fail: {data.get('reason') or 'model rejected'}"
            if isinstance(data, dict) and data.get("ok") is True:
                return True, str(data.get("reason") or "validated")
        except Exception as e:
            return True, f"validate_skip: {e}"  # don't block the mission on vision errors

    if changed:
        return True, "screen_changed"
    return True, "accepted_no_diff"


def _verify(goal: str, observation: str) -> tuple[bool, str]:
    from core import gemini
    data = gemini.as_json(
        f"Goal:{goal}\nScreen:{observation}\nJSON {{\"done\":true/false,\"reason\":\"short PT\"}}",
        tier=gemini.FAST, timeout_ms=16_000, default=None,
    )
    if isinstance(data, dict):
        return bool(data.get("done")), str(data.get("reason") or "")
    return False, "verificação indisponível"


# ── Entry ────────────────────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    global _last_hash, _last_obs, _last_mouse
    _last_hash, _last_obs = None, ""
    _last_mouse = _mouse_pos()
    deps = _probe_deps()
    _log(f"v5 deps={[k for k,v in deps.items() if v]}", player)

    queue_if_busy = str(parameters.get("queue") or "").lower() in ("1", "true", "yes", "sim")
    if not _acquire_lock():
        if queue_if_busy:
            return _enqueue({"parameters": parameters, "ts": time.time()})
        return (
            "Sir, já há uma missão desktop_agent em andamento (lock ativo). "
            "Espere, use queue=true para enfileirar, ou apague "
            "memory/desktop_missions/desktop_agent.lock se for lock morto."
        )

    try:
        return _run_inner(parameters, player, session_memory)
    finally:
        _release_lock()


def _run_inner(parameters: dict, player=None, session_memory=None) -> str:
    resume = str(parameters.get("resume") or "").lower() in ("1", "true", "yes", "sim")
    mission_id = (parameters.get("mission_id") or "").strip() or None
    goal = (parameters.get("goal") or parameters.get("task") or "").strip()
    dry = str(parameters.get("dry_run") or "").lower() in ("1", "true", "yes", "sim")
    confirm_only = str(parameters.get("confirm_steps") or "").lower() in ("1", "true", "yes", "sim")
    economy = str(parameters.get("economy") or "").lower() in ("1", "true", "yes", "sim")
    prefer_browser = str(parameters.get("prefer_browser") or "true").lower() not in ("0", "false", "no", "nao", "não")
    sticky = (parameters.get("sticky_window") or "").strip()

    mission: dict = {}
    if resume or mission_id:
        mission = _load_mission(mission_id) or {}
        if not mission:
            return "Sir, não há missão para retomar."
        goal = mission.get("goal") or goal
        sticky = sticky or (mission.get("sticky_window") or "")
        _log(f"RESUME {mission.get('id')}: {goal}", player)

    if not goal:
        return "Sir, informe goal ou resume=true."
    if _FORBIDDEN.search(goal):
        return "Sir, objetivo perigoso recusado."
    if not resume and _goal_too_vague(goal):
        return "Sir, objetivo vago. Seja específico (app + o que fazer + resultado esperado)."

    try:
        max_steps = int(parameters.get("max_steps") or mission.get("max_steps") or _DEFAULT_STEPS)
    except (TypeError, ValueError):
        max_steps = _DEFAULT_STEPS
    max_steps = max(1, min(max_steps, _MAX_STEPS))
    try:
        mon_pref = int(parameters.get("monitor") or mission.get("monitor") or 1)
    except (TypeError, ValueError):
        mon_pref = 1
    try:
        observe_every = int(parameters.get("observe_every") or (3 if economy else 2))
    except (TypeError, ValueError):
        observe_every = 3 if economy else 2
    observe_every = max(1, min(observe_every, 5))

    mon = _pick_monitor(mon_pref)
    history: list[str] = list(mission.get("history") or [])
    plan: list[dict] = list(mission.get("remaining_plan") or [])
    steps_run = int(mission.get("steps_run") or 0)
    last_action = mission.get("last_action") or ""
    last_result = mission.get("last_result") or ""
    final_reason = ""
    blocked = False

    _audit(f"START goal={goal!r} economy={economy} browser={prefer_browser}")
    _log(
        f"goal={goal!r} steps≤{max_steps} mon={mon.index} dpi={mon.dpi:.0f} "
        f"economy={economy} web={_goal_is_web(goal)}",
        player,
    )

    try:
        obs = _observe(goal, mon, last_action, last_result, force=True, economy=economy)
        history.append(f"OBS: {obs[:300]}")
        blocker = _detect_blocker(obs)
        if blocker and not resume:
            mid = _save_mission({
                "goal": goal, "status": "blocked", "blocker": blocker,
                "remaining_plan": [], "history": history[-30:],
                "steps_run": 0, "max_steps": max_steps, "monitor": mon_pref,
                "sticky_window": sticky,
            })
            return f"Barreira: {blocker}. Resolva e resume=true (id={mid})."
        if blocker and resume:
            return f"Ainda bloqueado: {blocker}."

        if not plan:
            plan = _build_plan(goal, obs, max_steps, prefer_browser)
        plan_txt = "; ".join(f"{i+1}.{s['action']}" for i, s in enumerate(plan))
        _log(f"Plan: {plan_txt}", player)
        history.append(f"PLAN: {plan_txt}")
        _audit(f"PLAN {plan_txt}")

        if confirm_only:
            mid = _save_mission({
                "goal": goal, "status": "awaiting_confirm",
                "remaining_plan": plan, "history": history[-30:],
                "steps_run": 0, "max_steps": max_steps, "monitor": mon_pref,
                "sticky_window": sticky,
            })
            lines = [
                f"{i+1}. [{s.get('risk','low')}] {s['action']} {s.get('args')} — {s.get('why')}"
                for i, s in enumerate(plan)
            ]
            return f"Plano ({mid}) — risco marcado:\n" + "\n".join(lines) + "\n\nExecute sem confirm_steps."

        i = 0
        while i < len(plan) and steps_run < max_steps:
            _heartbeat_lock()
            step = plan[i]
            action = step.get("action") or ""
            _log(f"Step {steps_run+1}: {action} risk={step.get('risk')} — {step.get('why')}", player)
            if action == "done":
                final_reason = step.get("why") or "done"
                break

            # ── Observar (fingerprint) → Agir → Validar ──────────────────
            before_fp = ""
            if not dry and action not in ("done", "wait", "sleep", "note"):
                before_fp = _screen_fingerprint(mon, economy=economy)

            result = _execute(step, mon, dry, sticky, goal, economy)
            steps_run += 1
            last_action = f"{action} {step.get('args')}"
            last_result = str(result)[:240]
            history.append(f"ACT{steps_run}: {last_action} → {last_result}")
            _audit(f"ACT {action} → {last_result[:120]}")
            _log(f"→ {last_result}", player)

            if not dry:
                ok_v, v_detail = _validate_action(
                    goal, step, mon, before_fp, last_result, economy=economy,
                )
                history.append(f"VAL{steps_run}: {'ok' if ok_v else 'fail'} — {v_detail[:160]}")
                _audit(f"VAL {action} → {v_detail[:120]}")
                if not ok_v:
                    last_result = f"validate_fail: {v_detail}"
                    _log(f"validate fail: {v_detail}", player)

            if steps_run % 4 == 0:
                _save_mission({
                    "goal": goal, "status": "running",
                    "remaining_plan": plan[i + 1:], "history": history[-40:],
                    "steps_run": steps_run, "max_steps": max_steps, "monitor": mon_pref,
                    "sticky_window": sticky, "last_action": last_action, "last_result": last_result,
                })

            should_obs = (
                action in (
                    "open_app", "click_desc", "double_click_desc", "drag", "hotkey",
                    "uia_click", "wait_for_app", "wait_for_screen", "wait_ready",
                    "scroll_until", "browser_goto", "browser_click_text", "browser_press",
                )
                or steps_run % observe_every == 0
                or _is_failure(last_result)
            )
            if should_obs and not economy or (economy and (steps_run % observe_every == 0 or _is_failure(last_result) or action.startswith("browser_") or action == "open_app")):
                time.sleep(0.12)
                obs = _observe(goal, mon, last_action, last_result,
                               force=_is_failure(last_result), economy=economy)
                history.append(f"OBS{steps_run}: {obs[:260]}")
                if _is_loading(obs) and action in ("open_app", "press", "hotkey", "click_desc", "browser_goto"):
                    wr = _adaptive_wait(mon, goal, economy, 28)
                    history.append(f"WAIT_READY: {wr}")
                    obs = _observe(goal, mon, last_action, wr, force=True, economy=economy)
                blocker = _detect_blocker(obs)
                if blocker:
                    blocked = True
                    final_reason = blocker
                    mid = _save_mission({
                        "goal": goal, "status": "blocked", "blocker": blocker,
                        "remaining_plan": plan[i + 1:], "history": history[-40:],
                        "steps_run": steps_run, "max_steps": max_steps, "monitor": mon_pref,
                        "sticky_window": sticky, "last_action": last_action, "last_result": last_result,
                    })
                    return f"Missão pausada: {blocker}\nresume=true id={mid} | passos={steps_run}"

            if _is_failure(last_result):
                if "interference" in last_result.lower():
                    final_reason = last_result
                    break
                obs = _observe(goal, mon, last_action, last_result, force=True, economy=economy)
                budget = max_steps - steps_run
                if budget <= 0:
                    final_reason = "sem passos após falha"
                    break
                plan = _replan(goal, obs, step, last_result, budget,
                               [h for h in history if h.startswith("ACT")])
                i = 0
                history.append("REPLAN: " + "; ".join(s["action"] for s in plan))
                continue
            i += 1
        else:
            if not final_reason:
                final_reason = f"limite de {max_steps} passos"

    except Exception as e:
        traceback.print_exc()
        _audit(f"CRASH {e}")
        return f"Sir, desktop_agent falhou: {e}"

    try:
        final_obs = _observe(goal, mon, last_action, last_result, force=True, economy=economy)
        done, verify_reason = _verify(goal, final_obs)
    except Exception:
        done, verify_reason = False, final_reason

    status = "concluído" if done else ("bloqueado" if blocked else "parcial")
    mid = _save_mission({
        "goal": goal,
        "status": "done" if done else ("blocked" if blocked else "partial"),
        "remaining_plan": [], "history": history[-40:],
        "steps_run": steps_run, "max_steps": max_steps, "monitor": mon_pref,
        "sticky_window": sticky, "last_action": last_action, "last_result": last_result,
        "result": verify_reason or final_reason,
    })
    _audit(f"END {status} id={mid} steps={steps_run}")
    summary = (
        f"Desktop agent v5 — {status}.\n"
        f"Objetivo: {goal}\n"
        f"Motivo: {verify_reason or final_reason}\n"
        f"Passos: {steps_run} | DPI: {mon.dpi:.0f} | Missão: {mid}"
        + (" | economy" if economy else "")
    )
    if dry:
        summary += "\n(dry-run)"
    _log(summary, player)
    return summary

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def desktop_agent(parameters=None, player=None, session_memory=None, **_ctx):
    """_LEGACY_TOOL handler — delegates to legacy run()."""
    params = parameters if isinstance(parameters, dict) else {}
    try:
        return run(params, player=player, session_memory=session_memory)
    except TypeError:
        try:
            return run(params, player=player)
        except TypeError:
            return run(params)


_LEGACY_TOOL = {
    "name": "desktop_agent",
    "description": ('Agente de desktop v5. Plano, resume pós-CAPTCHA, cliques com zoom, DPI,  scroll_until, Playwright para web, lock por PID, fila de missões,  economia de tokens, detecção de interferência e audit log.  goal | resume | mission_id | confirm_steps | dry_run | economy=true |  queue=true | sticky_window | monitor | max_steps | prefer_browser=true.  NÃO desliga/apaga/Wi-Fi; NÃO fura CAPTCHA/2FA.'),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "Objetivo"},
            "resume": {"type": "STRING", "description": "true = retoma missão pausada"},
            "mission_id": {"type": "STRING", "description": "ID da missão"},
            "max_steps": {"type": "NUMBER", "description": "padrão 12, máx 25"},
            "dry_run": {"type": "STRING", "description": "true = não executa"},
            "confirm_steps": {"type": "STRING", "description": "true = só plano"},
            "economy": {"type": "STRING", "description": "true = menos screenshots/Gemini"},
            "queue": {"type": "STRING", "description": "true = enfileira se ocupado"},
            "prefer_browser": {
                "type": "STRING",
                "description": "true (padrão) = usa Playwright se o goal for web",
            },
            "monitor": {"type": "NUMBER", "description": "1/2/0"},
            "observe_every": {"type": "NUMBER", "description": "padrão 2; economy força 3"},
            "sticky_window": {"type": "STRING", "description": "manter foco nesta janela"},
        },
        "required": [],
    },
    "handler": desktop_agent,
    "tier": "plugin",
    "risk": "autonomous",
}
