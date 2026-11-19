"""
image_upscale — super-resolution up to 4K (3840px on the long side).

Engines (auto-detect, best first)
---------------------------------
1. realesrgan-ncnn-vulkan binary (if on PATH)
2. Python realesrgan / basicsr (optional heavy install)
3. OpenCV LANCZOS4 + unsharp + denoise
4. Pillow LANCZOS multi-step

Project contract: returns outcome strings (done/failed/ask) with structured facts.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from core.outcome import done, failed, ask

_MAX_LONG = 3840  # 4K long side
_DEFAULT_LONG = 3840
_MIN_LONG = 64

_RES_PRESETS = {
    "1k": 1024,
    "2k": 2048,
    "4k": 3840,
    "1080p": 1920,
    "720p": 1280,
}


def _open_image(path: Path):
    from PIL import Image
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    return img


def _size_str(size: Tuple[int, int]) -> str:
    return "%dx%d" % (size[0], size[1])


def _resolve_target_long(params: dict, src_w: int, src_h: int) -> Tuple[int, Optional[float]]:
    """Return (target_long_side, explicit_scale_or_None)."""
    tr = str(params.get("target_resolution") or params.get("target_long") or "").strip().lower()
    scale = None
    if params.get("scale") not in (None, ""):
        try:
            scale = float(params.get("scale"))
        except (TypeError, ValueError):
            scale = None
    if tr in ("4x", "x4"):
        scale = 4.0
        return max(src_w, src_h) * 4, scale
    if tr in ("2x", "x2"):
        scale = 2.0
        return max(src_w, src_h) * 2, scale
    if tr in _RES_PRESETS:
        return _RES_PRESETS[tr], scale
    if tr.isdigit():
        return max(_MIN_LONG, min(_MAX_LONG, int(tr))), scale
    # default 4k long side
    try:
        if params.get("target_long"):
            return max(_MIN_LONG, min(_MAX_LONG, int(float(params.get("target_long"))))), scale
    except (TypeError, ValueError):
        pass
    return _DEFAULT_LONG, scale


def _target_size(w: int, h: int, target_long: int, scale: Optional[float]) -> Tuple[int, int]:
    long = max(w, h)
    if scale is not None and scale > 0:
        factor = float(scale)
    else:
        factor = target_long / float(long) if long else 1.0
    if scale is None and factor < 1.0:
        factor = 1.0
    nw = max(1, int(round(w * factor)))
    nh = max(1, int(round(h * factor)))
    long2 = max(nw, nh)
    if long2 > _MAX_LONG:
        f2 = _MAX_LONG / float(long2)
        nw = max(1, int(round(nw * f2)))
        nh = max(1, int(round(nh * f2)))
    return nw, nh


def _default_output(src: Path, w: int, h: int) -> Path:
    return src.with_name("%s_4k_%dx%d%s" % (src.stem, w, h, src.suffix or ".png"))


def _upscale_pillow(img, size):
    from PIL import Image
    cur = img
    tw, th = size
    while cur.size[0] * 2 < tw or cur.size[1] * 2 < th:
        step = (min(cur.size[0] * 2, tw), min(cur.size[1] * 2, th))
        if step == cur.size:
            break
        cur = cur.resize(step, Image.Resampling.LANCZOS)
    if cur.size != size:
        cur = cur.resize(size, Image.Resampling.LANCZOS)
    return cur, "pillow_lanczos"


def _upscale_opencv(img, size, mode: str = "photo"):
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except Exception:
        return None
    rgb = np.array(img.convert("RGB"))
    bgr = rgb[:, :, ::-1]
    # light denoise first on very small sources
    if min(img.size) < 500:
        bgr = cv2.fastNlMeansDenoisingColored(bgr, None, 3, 3, 7, 21)
    out = cv2.resize(bgr, size, interpolation=cv2.INTER_LANCZOS4)
    # adaptive unsharp
    blur = cv2.GaussianBlur(out, (0, 0), sigmaX=1.0 if mode != "anime" else 0.6)
    sharp = cv2.addWeighted(out, 1.35, blur, -0.35, 0)
    sharp = np.clip(sharp, 0, 255).astype("uint8")
    rgb_out = sharp[:, :, ::-1]
    return Image.fromarray(rgb_out), "opencv_lanczos4_unsharp"


def _upscale_realesrgan_bin(src: Path, dest: Path, mode: str, scale: int) -> Optional[str]:
    binary = shutil.which("realesrgan-ncnn-vulkan")
    if not binary:
        return None
    model = "realesrgan-x4plus-anime" if mode == "anime" else "realesrgan-x4plus"
    # binary scales by fixed model factor; we may need intermediate then resize
    try:
        cmd = [
            binary,
            "-i", str(src),
            "-o", str(dest),
            "-n", model,
            "-s", str(max(2, min(4, scale))),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0 and dest.is_file():
            return "realesrgan-ncnn-vulkan:%s" % model
    except Exception:
        return None
    return None


def _upscale_realesrgan_py(img, size, mode: str):
    # Optional Python package — soft fail
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return None
    try:
        # placeholder: many installs need weights; detect import only
        import realesrgan  # noqa: F401
    except Exception:
        return None
    return None


def image_upscale(parameters=None, **_ctx):
    params = parameters or {}
    action = str(params.get("action") or "upscale").strip().lower()
    t0 = time.perf_counter()

    if action in ("help", "status"):
        has_bin = bool(shutil.which("realesrgan-ncnn-vulkan"))
        try:
            import cv2  # noqa: F401
            has_cv2 = True
        except Exception:
            has_cv2 = False
        return done(
            "image_upscale",
            action="status",
            max_long_side=_MAX_LONG,
            default="4k",
            realesrgan_bin=has_bin,
            opencv=has_cv2,
            modes="photo|anime|texture_pbr",
        )

    path_raw = params.get("image_path") or params.get("path") or params.get("file")
    if not path_raw:
        return ask(
            "image_upscale",
            "image_path da imagem?",
            hint="image_path=/foto.jpg target_resolution=4k mode=photo",
        )

    src = Path(str(path_raw)).expanduser()
    if not src.is_file():
        return failed("image_upscale", "file not found: %s" % src)

    mode = str(params.get("mode") or "photo").strip().lower()
    if mode in ("texture", "pbr"):
        mode = "texture_pbr"
    if mode not in ("photo", "anime", "texture_pbr"):
        mode = "photo"

    try:
        tile = int(params.get("tile_size") or 512)
    except (TypeError, ValueError):
        tile = 512

    try:
        img = _open_image(src)
    except Exception as e:
        return failed("image_upscale", "cannot open image: %s" % e)

    w, h = img.size
    target_long, scale = _resolve_target_long(params, w, h)
    nw, nh = _target_size(w, h, target_long, scale)

    out_raw = params.get("output_path") or params.get("output") or params.get("out")
    dest = Path(str(out_raw)).expanduser() if out_raw else _default_output(src, nw, nh)
    dest.parent.mkdir(parents=True, exist_ok=True)

    engine = None
    out_img = None

    # Prefer Real-ESRGAN binary when upscale factor is meaningful
    factor = max(nw / max(w, 1), nh / max(h, 1))
    if factor >= 1.5:
        tmp_out = dest if dest.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else dest.with_suffix(".png")
        eng = _upscale_realesrgan_bin(src, tmp_out, mode, scale=4 if factor >= 3.5 else 2)
        if eng and tmp_out.is_file():
            # resize to exact target if needed
            try:
                got = _open_image(tmp_out)
                if got.size != (nw, nh):
                    got, _ = _upscale_pillow(got, (nw, nh))
                    got.save(dest)
                elif tmp_out != dest:
                    shutil.copy2(tmp_out, dest)
                engine = eng
                out_img = got if got.size == (nw, nh) else _open_image(dest)
            except Exception:
                engine = None

    if engine is None:
        result = _upscale_realesrgan_py(img, (nw, nh), mode)
        if result:
            out_img, engine = result

    if engine is None:
        result = _upscale_opencv(img, (nw, nh), mode=mode)
        if result:
            out_img, engine = result

    if engine is None:
        out_img, engine = _upscale_pillow(img, (nw, nh))

    try:
        save_kwargs = {}
        if dest.suffix.lower() in (".jpg", ".jpeg"):
            if out_img.mode == "RGBA":
                out_img = out_img.convert("RGB")
            save_kwargs = {"quality": 95, "optimize": True}
        elif dest.suffix.lower() == ".png" or not dest.suffix:
            if not dest.suffix:
                dest = dest.with_suffix(".png")
            save_kwargs = {"optimize": True}
        out_img.save(dest, **save_kwargs)
    except Exception as e:
        return failed("image_upscale", "save failed: %s" % e)

    ms = int((time.perf_counter() - t0) * 1000)
    final = out_img.size
    return done(
        "image_upscale",
        action="upscale",
        status="ok",
        original_resolution=_size_str((w, h)),
        final_resolution=_size_str(final),
        engine_used=engine,
        output_path=str(dest),
        execution_time_ms=ms,
        mode=mode,
        tile_size=tile,
        target_resolution=str(params.get("target_resolution") or "4k"),
        scale=round(max(final[0] / w, final[1] / h), 3),
    )


TOOL = {
    "name": "image_upscale",
    "description": (
        "Upscale / super-resolucao de imagens ate 4K (lado maior ate 3840px). "
        "Use quando o usuario pedir melhorar qualidade, 2K, 4K, upscale, deixar nitida. "
        "target_resolution: 2k|4k|4x|1080p. mode: photo|anime|texture_pbr. "
        "Motor: Real-ESRGAN (binario) se disponivel; senao OpenCV+unsharp; senao Pillow."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "upscale | status"},
            "image_path": {"type": "STRING", "description": "Caminho da imagem original"},
            "path": {"type": "STRING", "description": "Alias de image_path"},
            "target_resolution": {
                "type": "STRING",
                "description": "2k | 4k | 4x | 1080p | 720p | pixel number",
            },
            "mode": {"type": "STRING", "description": "photo | anime | texture_pbr"},
            "tile_size": {"type": "NUMBER", "description": "Default 512 (VRAM/RAM tiles)"},
            "output_path": {"type": "STRING", "description": "Saida opcional"},
            "output": {"type": "STRING", "description": "Alias de output_path"},
            "scale": {"type": "NUMBER", "description": "Fator explicito 2/3/4"},
            "backend": {"type": "STRING", "description": "auto | pillow | opencv | realesrgan"},
        },
        "required": [],
    },
    "handler": image_upscale,
    "tier": "core",
    "risk": "safe",
}
