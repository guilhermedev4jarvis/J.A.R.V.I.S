"""
core/face_auth.py — local face unlock via camera snapshot.

Approach
--------
1. Enrollment: capture a frame (or load an image), detect the largest face,
   store a compact embedding under memory/biometrics/face_profile.json.
2. Verification: new frame → same embedding → cosine similarity.

Detector / embedder priority
----------------------------
a) OpenCV Haar cascade + LBPH-like histogram embedding (always available if
   opencv-python is installed — already in requirements.txt).
b) If `face_recognition` (dlib) is installed, use 128-d encodings instead.

No images of the user leave the machine. Raw enrollment photos are optional
and stored only if save_image=True.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

_BASE = Path(__file__).resolve().parents[1]
_BIO_DIR = _BASE / "memory" / "biometrics"
_PROFILE = _BIO_DIR / "face_profile.json"
_DEFAULT_THRESHOLD = 0.82


@dataclass
class FaceScore:
    score: float
    accepted: bool
    threshold: float
    detail: str


def _ensure_dir() -> None:
    _BIO_DIR.mkdir(parents=True, exist_ok=True)


def _camera_index_default() -> int:
    """Read preferred camera index from config/api_keys.json if present."""
    try:
        cfg = _BASE / "config" / "api_keys.json"
        if cfg.is_file():
            import json
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return int(data.get("camera_index", 0))
    except Exception:
        pass
    return 0


def _open_camera(index: int | None = None):
    """Open the configured webcam with bounded, defensive attempts.

    On Windows prefer CAP_DSHOW (DirectShow): MSMF frequently fails to open by
    index and rejects CAP_PROP_OPEN_TIMEOUT_MSEC (property 53) with noisy
    ERROR/WARN lines. MSMF is tried without timeout params as a fallback, then
    CAP_ANY. By default only the configured index is tried; set
    JARVIS_CAMERA_SCAN=1 to probe indices 0..2 as well.
    """
    import cv2
    import platform
    import os

    # Disable MSMF hardware transforms — can hang or fail open on some drivers.
    os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

    if index is None:
        index = _camera_index_default()
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0

    indices = [index]
    # Always scan a few indices on Windows when the preferred one fails —
    # laptop IR / virtual cameras often shift the RGB device to 1.
    if os.environ.get("JARVIS_CAMERA_SCAN", "1") == "1":
        indices = list(dict.fromkeys([index, 0, 1, 2]))

    backends: list[int] = []
    if platform.system() == "Windows":
        # DirectShow first: most reliable for built-in / USB webcams on Win10/11.
        backends.append(getattr(cv2, "CAP_DSHOW", 700))
        backends.append(getattr(cv2, "CAP_MSMF", 1400))
        backends.append(getattr(cv2, "CAP_ANY", 0))
    else:
        backends.append(getattr(cv2, "CAP_ANY", 0))

    last_errors: list[str] = []
    for idx in indices:
        for backend in backends:
            cap = None
            try:
                # Never pass OPEN/READ timeout params on Windows backends —
                # MSMF logs "can't set property 53" and often fails to open.
                # Those properties are for FFmpeg/GStreamer, not DSHOW/MSMF.
                cap = cv2.VideoCapture(idx, backend)
                if cap is None or not cap.isOpened():
                    last_errors.append(f"index={idx}, backend={backend}: not opened")
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                    continue
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                # Warm a few frames so exposure settles, then require a real frame.
                frame = None
                ok = False
                for _ in range(6):
                    ok, frame = cap.read()
                    if ok and frame is not None and getattr(frame, "size", 0):
                        break
                if ok and frame is not None and getattr(frame, "size", 0):
                    return cap
                last_errors.append(f"index={idx}, backend={backend}: no frame")
                try:
                    cap.release()
                except Exception:
                    pass
            except Exception as exc:
                last_errors.append(
                    f"index={idx}, backend={backend}: {type(exc).__name__}: {exc}"
                )
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass
    raise RuntimeError(
        "Não foi possível abrir a webcam ou obter um frame válido. "
        "Feche Câmera/Teams/Discord/Zoom, confira Permissões de câmera do Windows "
        "(Configurações → Privacidade → Câmera) e, se necessário, ajuste "
        "camera_index em config/api_keys.json (tente 0 ou 1). "
        "Detalhes: " + " | ".join(last_errors[-6:])
    )



def _has_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def _has_face_recognition() -> bool:
    try:
        import face_recognition  # noqa: F401
        return True
    except Exception:
        return False


def _read_image(path: str | Path) -> np.ndarray:
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"cannot read image: {path}")
    return img


def _detect_face_bgr(img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) of largest face or None."""
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    # largest area
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(w), int(h)


def _embed_hist(img: np.ndarray, box: Tuple[int, int, int, int]) -> np.ndarray:
    """Simple robust embedding: grayscale resize + histogram + edges."""
    import cv2
    x, y, w, h = box
    face = img[y:y + h, x:x + w]
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (64, 64))
    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-9)
    edges = cv2.Canny(gray, 80, 160)
    edge_hist = cv2.calcHist([edges], [0], None, [16], [0, 256]).flatten()
    edge_hist = edge_hist / (edge_hist.sum() + 1e-9)
    vec = np.concatenate([hist, edge_hist]).astype(np.float32)
    vec /= (np.linalg.norm(vec) + 1e-9)
    return vec


def _embed_dlib(img: np.ndarray) -> Optional[np.ndarray]:
    import face_recognition
    rgb = img[:, :, ::-1]
    locs = face_recognition.face_locations(rgb)
    if not locs:
        return None
    encs = face_recognition.face_encodings(rgb, known_face_locations=locs[:1])
    if not encs:
        return None
    vec = np.asarray(encs[0], dtype=np.float32)
    vec /= (np.linalg.norm(vec) + 1e-9)
    return vec


def _embed_image(img: np.ndarray, *, allow_fullframe: bool = False) -> tuple[np.ndarray, str]:
    if _has_face_recognition():
        vec = _embed_dlib(img)
        if vec is not None:
            return vec, "face_recognition"
    if not _has_cv2():
        raise RuntimeError("opencv-python is required for face_auth")
    box = _detect_face_bgr(img)
    if box is None:
        if not allow_fullframe:
            raise RuntimeError("no face detected in image")
        # Fallback for controlled tests / unusual lighting: whole frame histogram.
        h, w = img.shape[:2]
        box = (0, 0, w, h)
        return _embed_hist(img, box), "opencv_hist_fullframe"
    return _embed_hist(img, box), "opencv_hist"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) + 1e-9) * (np.linalg.norm(b) + 1e-9)))


def enroll_from_image(path: str | Path, *, label: str = "owner") -> dict[str, Any]:
    path = Path(path)
    img = _read_image(path)
    vec, method = _embed_image(img)
    _ensure_dir()
    profile = {
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": method,
        "dim": int(vec.size),
        "vector": vec.tolist(),
        "threshold": _DEFAULT_THRESHOLD,
        "source": path.name,
    }
    _PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return {
        "enrolled": True,
        "label": label,
        "method": method,
        "dim": profile["dim"],
        "path": str(_PROFILE),
    }


def has_profile() -> bool:
    return _PROFILE.is_file()


def load_profile() -> Optional[dict]:
    if not _PROFILE.is_file():
        return None
    try:
        return json.loads(_PROFILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def verify_image(path: str | Path, *, threshold: Optional[float] = None) -> FaceScore:
    profile = load_profile()
    if not profile or not profile.get("vector"):
        return FaceScore(0.0, False, _DEFAULT_THRESHOLD, "no_profile")
    thr = float(threshold if threshold is not None else profile.get("threshold", _DEFAULT_THRESHOLD))
    img = _read_image(path)
    try:
        vec, method = _embed_image(img)
    except Exception as e:
        return FaceScore(0.0, False, thr, f"embed_failed: {e}")
    ref = np.asarray(profile["vector"], dtype=np.float32)
    if ref.shape != vec.shape:
        return FaceScore(0.0, False, thr, f"dim_mismatch profile={ref.shape} probe={vec.shape} method={method}")
    score = _cosine(ref, vec)
    ok = score >= thr
    return FaceScore(score, ok, thr, "match" if ok else "below_threshold")


@dataclass
class LivenessResult:
    ok: bool
    detail: str
    motion_score: float = 0.0
    ear_delta: float = 0.0
    frames: int = 0


def _eye_aspect_proxy(gray_face: np.ndarray) -> float:
    """Cheap eye-openness proxy without dlib landmarks.

    Uses Haar eye cascade count + mean intensity variance in the upper half of
    the face ROI. Not a true EAR, but detects a static printed photo poorly
    when combined with inter-frame motion.
    """
    import cv2
    h, w = gray_face.shape[:2]
    upper = gray_face[0 : max(1, h // 2), :]
    eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye.xml"
    )
    eyes = eye_cascade.detectMultiScale(upper, 1.1, 3, minSize=(12, 12))
    if len(eyes) == 0:
        return 0.0
    # mean relative eye height as openness proxy
    scores = []
    for (_x, _y, ew, eh) in eyes[:2]:
        scores.append(float(eh) / float(max(1, h)))
    return float(sum(scores) / len(scores))


def check_liveness(
    index: int = 0,
    *,
    frames: int = 12,
    min_motion: float = 1.8,
    require_ear_change: bool = True,
) -> tuple[LivenessResult, Optional[np.ndarray]]:
    """Capture a short burst; require natural micro-motion (anti photo/screen).

    Returns (liveness, last_frame_bgr).
    """
    import cv2
    import time as _time

    cap = _open_camera(index)
    try:
        buf: list[np.ndarray] = []
        ears: list[float] = []
        # discard a few frames while exposure settles
        for _ in range(4):
            cap.read()
            _time.sleep(0.03)
        for _ in range(max(6, frames)):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            buf.append(frame)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face = _detect_face_bgr(frame)
            if face is not None:
                x, y, w, h = face
                roi = gray[y : y + h, x : x + w]
                ears.append(_eye_aspect_proxy(roi))
            _time.sleep(0.05)
        if len(buf) < 4:
            return LivenessResult(False, "too_few_frames", frames=len(buf)), None

        # Inter-frame mean absolute difference (downscaled)
        motions = []
        prev = cv2.resize(cv2.cvtColor(buf[0], cv2.COLOR_BGR2GRAY), (96, 96)).astype(np.float32)
        for fr in buf[1:]:
            cur = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (96, 96)).astype(np.float32)
            motions.append(float(np.mean(np.abs(cur - prev))))
            prev = cur
        motion_score = float(sum(motions) / max(1, len(motions)))

        ear_delta = 0.0
        if len(ears) >= 3:
            ear_delta = float(max(ears) - min(ears))

        # Static photo / frozen screen: near-zero motion
        if motion_score < min_motion:
            return (
                LivenessResult(
                    False,
                    "static_or_photo_suspected",
                    motion_score=motion_score,
                    ear_delta=ear_delta,
                    frames=len(buf),
                ),
                buf[-1],
            )

        # Optional: require some variation in eye-region proxy (blink / expression)
        if require_ear_change and len(ears) >= 4 and ear_delta < 0.004 and motion_score < (min_motion * 2.5):
            return (
                LivenessResult(
                    False,
                    "no_eye_micro_motion",
                    motion_score=motion_score,
                    ear_delta=ear_delta,
                    frames=len(buf),
                ),
                buf[-1],
            )

        return (
            LivenessResult(
                True,
                "live",
                motion_score=motion_score,
                ear_delta=ear_delta,
                frames=len(buf),
            ),
            buf[-1],
        )
    finally:
        cap.release()


def capture_from_camera(index: int | None = None, settle_frames: int = 8) -> np.ndarray:
    """Grab a single BGR frame from the default webcam (Windows: prefers DSHOW)."""
    import cv2
    cap = _open_camera(index)
    try:
        frame = None
        for _ in range(max(1, settle_frames)):
            ok, frame = cap.read()
            if ok and frame is not None:
                pass
            else:
                # one more soft retry after short settle
                import time as _time
                _time.sleep(0.05)
                ok, frame = cap.read()
        if frame is None:
            raise RuntimeError("camera read failed — nenhum frame válido")
        return frame
    finally:
        cap.release()


def enroll_from_camera(index: int | None = None, *, label: str = "owner") -> dict[str, Any]:
    frame = capture_from_camera(index)
    tmp = _BIO_DIR / "_enroll_face.jpg"
    _ensure_dir()
    import cv2
    cv2.imwrite(str(tmp), frame)
    try:
        return enroll_from_image(tmp, label=label)
    finally:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)


def verify_from_camera(
    index: int | None = None,
    *,
    threshold: Optional[float] = None,
    require_liveness: bool = True,
    liveness_frames: int = 12,
) -> FaceScore:
    """Verify face from webcam. By default runs anti-spoofing liveness first."""
    live = LivenessResult(True, "skipped")
    frame: Optional[np.ndarray] = None
    if require_liveness:
        live, frame = check_liveness(index, frames=liveness_frames)
        if not live.ok:
            return FaceScore(
                0.0,
                False,
                threshold if threshold is not None else _DEFAULT_THRESHOLD,
                "liveness_failed:%s motion=%.2f ear_delta=%.4f"
                % (live.detail, live.motion_score, live.ear_delta),
            )
    if frame is None:
        frame = capture_from_camera(index)

    import cv2
    tmp = _BIO_DIR / "_probe_face.jpg"
    _ensure_dir()
    cv2.imwrite(str(tmp), frame)
    try:
        score = verify_image(tmp, threshold=threshold)
        if score.accepted and require_liveness:
            score = FaceScore(
                score.score,
                True,
                score.threshold,
                "match+live motion=%.2f" % live.motion_score,
            )
        return score
    finally:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)


def clear_profile() -> bool:
    if _PROFILE.is_file():
        _PROFILE.unlink()
        return True
    return False
