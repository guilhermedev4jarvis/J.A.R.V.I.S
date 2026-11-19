"""
Plugin: weather_report — previsão do tempo FALADA (Open-Meteo, sem chave de API).

Coloque este arquivo em:  plugins/weather_report.py
(Apague qualquer weather_report.py antigo em plugins/ que só abria o Google.)
"""
from __future__ import annotations

from core.outcome import ask, done, failed

from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_WMO = {
    0: "céu limpo", 1: "principalmente limpo", 2: "parcialmente nublado",
    3: "nublado", 45: "neblina", 48: "neblina com geada",
    51: "garoa leve", 53: "garoa moderada", 55: "garoa intensa",
    61: "chuva leve", 63: "chuva moderada", 65: "chuva forte",
    71: "neve leve", 73: "neve moderada", 75: "neve intensa",
    80: "pancadas de chuva leves", 81: "pancadas de chuva moderadas",
    82: "pancadas de chuva fortes", 95: "tempestade",
    96: "tempestade com granizo leve", 99: "tempestade com granizo forte",
}

_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_FC = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 10


def _cond(code) -> str:
    try:
        return _WMO.get(int(code), "condição indefinida")
    except Exception:
        return "condição indefinida"


def _geocode(cidade: str) -> Optional[dict]:
    r = requests.get(
        _GEO,
        params={"name": cidade, "count": 5, "language": "pt", "format": "json"},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        return None
    for item in results:
        if (item.get("country_code") or "").upper() == "BR":
            return item
    return results[0]


def _forecast(lat: float, lon: float) -> dict:
    r = requests.get(
        _FC,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m,precipitation"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum"
            ),
            "timezone": "auto",
            "forecast_days": 7,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _norm_quando(q: str) -> str:
    q = (q or "hoje").strip().lower()
    mapa = {
        "agora": "agora", "now": "agora",
        "hoje": "hoje", "today": "hoje",
        "amanha": "amanhã", "amanhã": "amanhã", "tomorrow": "amanhã",
        "semana": "semana", "esta semana": "semana", "essa semana": "semana",
        "week": "semana", "this week": "semana",
    }
    return mapa.get(q, q)


def _agora(cur: dict, nome: str) -> str:
    temp = cur.get("temperature_2m")
    sens = cur.get("apparent_temperature")
    umid = cur.get("relative_humidity_2m")
    vento = cur.get("wind_speed_10m")
    precip = cur.get("precipitation") or 0
    code = cur.get("weather_code", 0)
    partes = [f"Em {nome} agora está {_cond(code)}"]
    if temp is not None:
        partes.append(f"com {temp:.0f} graus")
    if sens is not None and temp is not None and abs(sens - temp) >= 2:
        partes.append(f"(sensação de {sens:.0f})")
    if umid is not None:
        partes.append(f"umidade de {umid:.0f}%")
    if vento is not None and vento >= 15:
        partes.append(f"vento de {vento:.0f} km/h")
    if precip and precip > 0.1:
        partes.append(f"e chovendo ({precip:.1f} mm)")
    t = ", ".join(partes) + "."
    return t[0].upper() + t[1:]


def _dia(daily: dict, idx: int, nome: str, rotulo: str) -> str:
    try:
        tmax = daily["temperature_2m_max"][idx]
        tmin = daily["temperature_2m_min"][idx]
        code = daily["weather_code"][idx]
        chance = (daily.get("precipitation_probability_max") or [None])[idx]
        chuva = (daily.get("precipitation_sum") or [0])[idx] or 0
    except Exception:
        return f"Não consegui a previsão de {rotulo} para {nome}."
    partes = [f"{rotulo} em {nome}: {_cond(code)}"]
    partes.append(f"máxima de {tmax:.0f} e mínima de {tmin:.0f} graus")
    if chance is not None and chance >= 30:
        partes.append(f"chance de chuva de {chance:.0f}%")
    if chuva >= 1:
        partes.append(f"com cerca de {chuva:.1f} mm")
    t = ", ".join(partes) + "."
    return t[0].upper() + t[1:]


def _semana(daily: dict, nome: str) -> str:
    dias = daily.get("time") or []
    if not dias:
        return f"Não consegui a previsão semanal para {nome}."
    nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    linhas = [f"Previsão para os próximos dias em {nome}:"]
    for i, data_str in enumerate(dias[:5]):
        try:
            dt = datetime.strptime(data_str, "%Y-%m-%d")
            tmax = daily["temperature_2m_max"][i]
            tmin = daily["temperature_2m_min"][i]
            code = daily["weather_code"][i]
            chance = (daily.get("precipitation_probability_max") or [None])[i]
            trecho = f"{nomes[dt.weekday()]}: {_cond(code)}, {tmin:.0f} a {tmax:.0f}°"
            if chance is not None and chance >= 40:
                trecho += f", {chance:.0f}% de chuva"
            linhas.append(trecho)
        except Exception:
            continue
    return ". ".join(linhas) + "."


def run(parameters: dict, player=None, session_memory=None) -> str:
    if not _HAS_REQUESTS:
        return "Sir, falta o pacote requests. Rode: pip install requests"

    cidade = (
        parameters.get("cidade")
        or parameters.get("city")
        or ""
    )
    cidade = str(cidade).strip()
    quando = _norm_quando(
        parameters.get("quando")
        or parameters.get("time")
        or "hoje"
    )

    if not cidade:
        return ask(
            "weather_report",
            "preciso da cidade. Por exemplo: clima em Sao Paulo, ou previsao para Curitiba amanha.",
        )

    try:
        geo = _geocode(cidade)
    except Exception as e:
        return f"Sir, não consegui localizar a cidade agora: {e}"

    if not geo:
        return f"Sir, não encontrei a cidade '{cidade}'. Tente o nome completo."

    nome = geo.get("name") or cidade
    admin = geo.get("admin1") or ""
    if admin and admin.lower() not in nome.lower():
        nome = f"{nome}, {admin}"

    try:
        data = _forecast(float(geo["latitude"]), float(geo["longitude"]))
    except Exception as e:
        return f"Sir, a previsão falhou no momento: {e}"

    current = data.get("current") or {}
    daily = data.get("daily") or {}

    try:
        if quando == "agora":
            msg = _agora(current, nome)
        elif quando == "amanhã":
            msg = _dia(daily, 1, nome, "Amanhã")
        elif quando == "semana":
            msg = _semana(daily, nome)
        else:  # hoje
            msg = _agora(current, nome) + " " + _dia(daily, 0, nome, "Para o restante do dia")
    except Exception as e:
        return f"Sir, erro ao montar a previsão: {e}"

    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass
    return msg

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def weather_report(parameters=None, player=None, session_memory=None, **_ctx):
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
    "name": "weather_report",
    "description": ('Retorna a previsão do tempo falada: temperatura, condição, umidade,  vento e chance de chuva. Use quando o usuário perguntar sobre clima,  tempo, temperatura, se vai chover, previsão do tempo. '),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cidade": {
                "type": "STRING",
                "description": "Nome da cidade (ex: São Paulo, Curitiba, Rio de Janeiro)",
            },
            "city": {
                "type": "STRING",
                "description": "City name (alias em inglês de cidade)",
            },
            "quando": {
                "type": "STRING",
                "description": "agora | hoje | amanhã | esta semana (padrão: hoje)",
            },
            "time": {
                "type": "STRING",
                "description": "Period alias: now, today, tomorrow, week",
            },
        },
        "required": [],
    },
    "handler": weather_report,
    "tier": "plugin",
    "risk": "review",
}
