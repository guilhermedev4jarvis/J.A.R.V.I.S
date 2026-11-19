#!/usr/bin/env python3
"""
J.A.R.V.I.S. / MARK LXI — setup is only a bridge to requirements*.txt.

    python setup.py                  # requirements.txt
    python setup.py --local          # requirements.txt + requirements.txt
    python setup.py --heavy          # requirements.txt + requirements.txt
    python setup.py --local --heavy  # core + local + heavy
    python setup.py --browsers       # playwright chromium + firefox
    python setup.py --all            # local + heavy + browsers

Heavy wheels stay behind flags. Edit requirements*.txt — not this file —
to change package sets.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

OS = platform.system()
HERE = Path(__file__).resolve().parent

MIN_PY = (3, 11)
MAX_PY = (3, 13)

REQ_CORE = HERE / "requirements.txt"


def _pip_install_file(req: Path) -> None:
    """Install one requirements file via pip; abort if the file is missing."""
    if not req.is_file():
        print(f"\n❌ Arquivo obrigatório ausente: {req}")
        print(f"   Esperado em: {req.resolve()}")
        raise SystemExit(1)
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(req)]
    print(f"\n▶ Instalando {req.name}")
    print(f"  $ {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Falha ao instalar {req.name} (exit {e.returncode})")
        raise SystemExit(e.returncode) from e
    print(f"✅ {req.name} instalado.")


def _install_browsers() -> None:
    cmd = [sys.executable, "-m", "playwright", "install", "chromium", "firefox"]
    print("\n▶ Playwright browsers (chromium + firefox)")
    print(f"  $ {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("✅ Browsers instalados.")
    except subprocess.CalledProcessError as e:
        print("\n⚠️  Playwright browsers não instalados. Retry:")
        print(f"   {sys.executable} -m playwright install chromium firefox")
        raise SystemExit(e.returncode) from e
    except FileNotFoundError:
        print("\n⚠️  Módulo playwright ausente — instale o core primeiro.")
        raise SystemExit(1)


def _check_python() -> None:
    v = sys.version_info[:2]
    if v < MIN_PY:
        print(
            f"\n❌ Python {v[0]}.{v[1]} — necessário ≥ {MIN_PY[0]}.{MIN_PY[1]}.\n"
            f"   py -{MIN_PY[0]}.{MIN_PY[1]} setup.py   (Windows)\n"
            f"   python{MIN_PY[0]}.{MIN_PY[1]} setup.py (macOS / Linux)"
        )
        raise SystemExit(1)
    if v > MAX_PY:
        print(
            f"\n⚠️  Python {v[0]}.{v[1]} é mais novo que o testado "
            f"({MAX_PY[0]}.{MAX_PY[1]}). Continuando."
        )


def _check_assets() -> None:
    face = HERE / "core" / "face_model.obj"
    if not face.is_file():
        print(
            "\n⚠️  core/face_model.obj ausente — avatar 3D pode degradar.\n"
            "   O restante do app continua funcional."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="Instalador J.A.R.V.I.S. / MARK LXI (ponte para requirements*.txt)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Instala também requirements.txt (voz/OCR/BM25 offline)",
    )
    parser.add_argument(
        "--heavy",
        action="store_true",
        help="Instala também requirements.txt (Real-ESRGAN, chroma, MCP…)",
    )
    parser.add_argument(
        "--browsers",
        action="store_true",
        help="Instala motores Playwright (chromium + firefox)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Atalho: --local --heavy --browsers",
    )
    args = parser.parse_args(argv)

    if args.all:
        args.local = True
        args.heavy = True
        args.browsers = True

    print("=" * 60)
    print(f" MARK LXI setup  ·  {OS}  ·  Python {sys.version.split()[0]}")
    print("=" * 60)

    _check_python()
    _check_assets()

    # Sempre o core primeiro
    _pip_install_file(REQ_CORE)

    if args.local or args.heavy:
        # Unified requirements.txt only
        _pip_install_file(REQ_CORE)
    if args.browsers:
        _install_browsers()

    print("\n" + "=" * 60)
    print(" Setup concluído.")
    layers = ["core"]
    if args.local:
        layers.append("local")
    if args.heavy:
        layers.append("heavy")
    if args.browsers:
        layers.append("browsers")
    print(" Camadas: " + " + ".join(layers))
    print(" Próximo:  python -m main")
    print("=" * 60)
    return 0




# ── setuptools packaging (pip install -e .) ───────────────────────────────────
def _read_requirements(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # drop environment markers for install_requires simplicity when after ;
        pkg = line.split(";")[0].strip()
        if pkg and not pkg.startswith("-"):
            out.append(line)  # keep markers for pip
    return out


def _setuptools_meta() -> None:
    try:
        from setuptools import setup, find_packages
    except ImportError:
        print("setuptools ausente — pulando metadata pip (use: pip install setuptools)")
        return
    setup(
        name="jarvis-mark-lxi",
        version="61.0.0",
        description="J.A.R.V.I.S. — MARK LXI (61) offline-first desktop assistant",
        author="Guilherme",
        license="CC-BY-NC-4.0",
        packages=find_packages(exclude=("tests", "tests.*")),
        packages=["main", "ui"],
        install_requires=_read_requirements(REQ_CORE),
        python_requires=">=3.11",
        entry_points={
            "console_scripts": [
                "jarvis=main.lifecycle:main",
                "jarvis-local=main.lifecycle:main",
            ],
        },
        include_package_data=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
