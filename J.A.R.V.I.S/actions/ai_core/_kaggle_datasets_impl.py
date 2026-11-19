"""kaggle_datasets — autenticação via .env + download Burglary (UCF-Crime)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Optional

from core.outcome import done, failed, ask
from actions.security._security_vision import audit, speak_short

_BASE = Path(__file__).resolve().parents[2]
_DEST = _BASE / "memory" / "teste_cameras" / "Burglary"
_DATASET = "odins0n/ucf-crime-dataset"
UCF_CRIME_CLASSES = ["Abuse","Arrest","Arson","Assault","Burglary","Explosion","Fighting","Normal","RoadAccidents","Robbery","Shooting","Shoplifting","Stealing","Vandalism"]
UCF_TEST = "Burglary"  # notebook path: Test/Burglary, Train/Burglary



def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d or "").strip().strip('"').strip("'")


def ensure_kaggle_credentials() -> dict:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    """Export KAGGLE_* from .env and materialize ~/.kaggle/kaggle.json when possible."""
    user = _env("KAGGLE_USERNAME")
    key = _env("KAGGLE_KEY") or _env("KAGGLE_API_TOKEN")
    if user:
        os.environ["KAGGLE_USERNAME"] = user
    if key:
        os.environ["KAGGLE_KEY"] = key
        # Some setups use token-only auth
        os.environ.setdefault("KAGGLE_API_TOKEN", key)

    home = Path(os.path.expanduser("~")) / ".kaggle"
    cfg = home / "kaggle.json"
    if user and key:
        try:
            home.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({"username": user, "key": key}), encoding="utf-8")
            try:
                os.chmod(cfg, 0o600)
            except Exception:
                pass
        except Exception as e:
            audit("kaggle_cfg_write_fail", tool="kaggle_datasets", extra={"error": str(e)[:120]})
    ok = bool((_env("KAGGLE_USERNAME") and (_env("KAGGLE_KEY") or _env("KAGGLE_API_TOKEN"))) or cfg.is_file())
    return {"ok": ok, "username": bool(user or _env("KAGGLE_USERNAME")), "has_key": bool(key or cfg.is_file())}


def _help_msg() -> str:
    return (
        "Credenciais Kaggle ausentes, Senhor. Em kaggle.com/settings/api crie um token, "
        "depois no .env defina KAGGLE_USERNAME e KAGGLE_KEY (ou KAGGLE_API_TOKEN)."
    )


def _run_kaggle(args: list[str], timeout: int = 300) -> dict:
    try:
        r = subprocess.run(
            ["kaggle"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "code": r.returncode,
            "stdout": (r.stdout or "")[-4000:],
            "stderr": (r.stderr or "")[-2000:],
        }
    except FileNotFoundError:
        # fallback: python -m kaggle
        try:
            r = subprocess.run(
                [os.environ.get("PYTHON", "python"), "-m", "kaggle"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "ok": r.returncode == 0,
                "code": r.returncode,
                "stdout": (r.stdout or "")[-4000:],
                "stderr": (r.stderr or "")[-2000:],
            }
        except Exception as e:
            return {"ok": False, "reason": f"kaggle_cli_missing:{e}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


def download_burglary_sample(limit: int = 12) -> dict:
    """Download Burglary sample files into memory/teste_cameras/Burglary/."""
    cred = ensure_kaggle_credentials()
    if not cred.get("ok"):
        return {"ok": False, "reason": "no_credentials", "help": _help_msg()}

    _DEST.mkdir(parents=True, exist_ok=True)
    work = _BASE / "memory" / "tmp_kaggle_ucf"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # List files and filter Test/Burglary (and Train/Burglary as fallback)
    listed = _run_kaggle(["datasets", "files", "-d", _DATASET], timeout=120)
    names = []
    blob = (listed.get("stdout") or "") + "\n" + (listed.get("stderr") or "")
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        # kaggle table lines often contain path-like tokens
        for part in line.replace("\\", "/").split():
            if "Burglary" in part and (part.endswith(".png") or part.endswith(".jpg") or part.endswith(".jpeg") or part.endswith(".mp4") or "/" in part):
                names.append(part.strip())
    # Prefer Test/Burglary
    preferred = [n for n in names if "Test/Burglary" in n or "test/Burglary" in n]
    if not preferred:
        preferred = [n for n in names if "Burglary" in n]
    preferred = preferred[: max(1, int(limit))]

    downloaded = []
    if preferred:
        for fpath in preferred:
            out = _run_kaggle(
                ["datasets", "download", "-d", _DATASET, "-f", fpath, "-p", str(work), "--force"],
                timeout=180,
            )
            if out.get("ok"):
                downloaded.append(fpath)
            else:
                audit("kaggle_file_fail", tool="kaggle_datasets", extra={"file": fpath, "err": out.get("stderr", "")[:160]})
    else:
        # Full dataset download is heavy — try zip then extract Burglary only
        out = _run_kaggle(
            ["datasets", "download", "-d", _DATASET, "-p", str(work), "--force"],
            timeout=600,
        )
        if not out.get("ok"):
            return {
                "ok": False,
                "reason": out.get("reason") or out.get("stderr") or "download_failed",
                "list": listed,
                "help": _help_msg() if "401" in str(out) or "403" in str(out) else None,
            }

    # Unzip any archives and copy Burglary media into destination
    for z in work.rglob("*.zip"):
        try:
            with zipfile.ZipFile(z, "r") as zf:
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if "Burglary" not in name:
                        continue
                    if not any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".mp4", ".avi")):
                        continue
                    target = _DEST / Path(name).name
                    with zf.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    downloaded.append(str(target.name))
        except Exception as e:
            audit("kaggle_unzip_fail", tool="kaggle_datasets", extra={"error": str(e)[:120]})

    # Copy loose files already extracted
    for media in list(work.rglob("*")):
        if not media.is_file():
            continue
        if "Burglary" not in str(media).replace("\\", "/") and media.parent.name != "Burglary":
            # still accept if only burglary folder content after selective -f
            if media.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".mp4", ".avi"):
                continue
        if media.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".mp4", ".avi"):
            dest = _DEST / media.name
            try:
                shutil.copy2(media, dest)
                downloaded.append(media.name)
            except Exception:
                pass

    count = len([p for p in _DEST.iterdir() if p.is_file()]) if _DEST.is_dir() else 0
    ok = count > 0
    audit("kaggle_burglary_download", tool="kaggle_datasets", extra={"files": count, "ok": ok})
    return {
        "ok": ok,
        "dataset": _DATASET,
        "dest": str(_DEST.relative_to(_BASE)),
        "files_on_disk": count,
        "downloaded_refs": downloaded[:30],
        "list_ok": listed.get("ok"),
    }


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "download_burglary").lower()
    if action in ("setup_help", "help"):
        return done("kaggle_datasets", action="setup_help", message=_help_msg())
    if action == "status":
        cred = ensure_kaggle_credentials()
        count = len([x for x in _DEST.iterdir() if x.is_file()]) if _DEST.is_dir() else 0
        return done("kaggle_datasets", action="status", credentials=cred, burglary_files=count, dest=str(_DEST))
    # download
    limit = int(p.get("limit") or 12)
    speak_short("Baixando amostra de arrombamento do Kaggle, Senhor.", player=player)
    result = download_burglary_sample(limit=limit)
    if not result.get("ok"):
        if result.get("reason") == "no_credentials":
            speak_short("Credenciais do Kaggle não configuradas, Senhor.", player=player)
            return failed("kaggle_datasets", _help_msg(), **{k: v for k, v in result.items() if k != "reason"})
        return failed("kaggle_datasets", str(result.get("reason") or "falha no download"), **result)
    speak_short(f"Amostra pronta com {result.get('files_on_disk')} arquivos, Senhor.", player=player)
    return done("kaggle_datasets", action="download_burglary", **result)
