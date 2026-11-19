"""
Plugin: baixar_arquivo — baixa um arquivo de uma URL e salva na pasta desejada.

Exemplos de fala:
- "baixa esse PDF e joga na pasta de treinos"
- "download https://... pra config/treinador_base"
- "baixa o arquivo X e salva em D:/downloads"
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

# Pastas relativas conhecidas (atalhos em português)
_ATALHOS = {
    "treinos": "config/treinador_base",
    "treino": "config/treinador_base",
    "treinador": "config/treinador_base",
    "treinador_base": "config/treinador_base",
    "plugins": "plugins",
    "pending": "plugins/pending",
    "downloads": None,  # resolvido em runtime
    "download": None,
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_downloads() -> Path:
    """Pasta de downloads padrão (Windows do Gui = D:/downloads, senão ~/Downloads)."""
    # Preferência do perfil do usuário
    win = Path("D:/downloads")
    if win.parent.exists():  # D: existe
        win.mkdir(parents=True, exist_ok=True)
        return win
    home = Path.home() / "Downloads"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _resolve_pasta(pasta: str) -> Path:
    pasta = (pasta or "").strip().strip('"').strip("'")
    if not pasta:
        return _default_downloads()

    key = pasta.lower().replace("\\", "/").strip("/")
    if key in _ATALHOS:
        rel = _ATALHOS[key]
        if rel is None:
            return _default_downloads()
        return (_project_root() / rel).resolve()

    p = Path(pasta)
    if p.is_absolute():
        return p
    # relativo ao projeto
    return (_project_root() / pasta).resolve()


def _nome_da_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name
    if name and "." in name and len(name) < 180:
        # limpa query residual
        name = name.split("?")[0]
        return name
    return "arquivo_baixado.bin"


def _safe_name(name: str) -> str:
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:180] or "arquivo_baixado.bin"


def run(parameters: dict, player=None, session_memory=None) -> str:
    url = (parameters.get("url") or "").strip()
    pasta = (parameters.get("pasta") or "").strip()
    nome = (parameters.get("nome") or "").strip()

    if not url:
        return "Me passa a URL do arquivo, senhor."
    if not url.startswith(("http://", "https://")):
        return "A URL precisa começar com http:// ou https://"

    dest_dir = _resolve_pasta(pasta)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return f"Não consegui criar/acessar a pasta {dest_dir}: {e}"

    filename = _safe_name(nome) if nome else _safe_name(_nome_da_url(url))
    dest = dest_dir / filename

    if player:
        try:
            player.write_log(f"JARVIS: Baixando → {filename} em {dest_dir}")
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            # se o servidor mandar outro nome no Content-Disposition
            cd = resp.headers.get("Content-Disposition") or ""
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
            if m and not nome:
                filename = _safe_name(unquote(m.group(1).strip()))
                dest = dest_dir / filename

            data = resp.read()
            if len(data) < 50:
                return (
                    f"Download veio vazio ou bloqueado ({len(data)} bytes). "
                    f"O site pode estar pedindo login ou bloqueando."
                )

            dest.write_bytes(data)

    except Exception as e:
        return f"Falha no download: {e}"

    tamanho = dest.stat().st_size
    if tamanho > 1_000_000:
        tam_txt = f"{tamanho / 1_000_000:.1f} MB"
    elif tamanho > 1000:
        tam_txt = f"{tamanho / 1000:.0f} KB"
    else:
        tam_txt = f"{tamanho} bytes"

    if player:
        try:
            player.write_log(f"JARVIS: Salvo {dest.name} ({tam_txt})")
        except Exception:
            pass

    return f"Baixei e salvei: {dest} ({tam_txt})"

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def baixar_arquivo(parameters=None, player=None, session_memory=None, **_ctx):
    """TOOL handler — delegates to legacy run()."""
    params = parameters if isinstance(parameters, dict) else {}
    try:
        return run(params, player=player, session_memory=session_memory)
    except TypeError:
        try:
            return run(params, player=player)
        except TypeError:
            return run(params)


TOOL = {
    "name": "baixar_arquivo",
    "description": ('Baixa um arquivo da internet e salva na pasta que o usuário indicar.  Use quando o usuário disser  ,  ,  ,   , etc.  Precisa da URL e, se possível, da pasta de destino.  Se a pasta não for dita, usa a pasta de downloads padrão do sistema.'),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {
                "type": "STRING",
                "description": "URL completa do arquivo (http ou https)",
            },
            "pasta": {
                "type": "STRING",
                "description": (
                    "Pasta de destino. Pode ser caminho absoluto "
                    "(ex: D:/downloads) ou relativo ao projeto "
                    "(ex: config/treinador_base). "
                    "Se vazio, usa a pasta de downloads padrão."
                ),
            },
            "nome": {
                "type": "STRING",
                "description": (
                    "Nome do arquivo final (opcional). "
                    "Se vazio, usa o nome que vem da URL."
                ),
            },
        },
        "required": ["url"],
    },
    "handler": baixar_arquivo,
    "tier": "plugin",
    "risk": "review",
}
