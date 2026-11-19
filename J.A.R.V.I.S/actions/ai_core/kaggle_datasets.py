"""Action: kaggle_datasets — download seletivo de amostras (ex: UCF-Crime Burglary)."""
from __future__ import annotations

from core.outcome import failed


def kaggle_datasets(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._kaggle_datasets_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("kaggle_datasets", f"impl error: {e}")


TOOL = {
    "name": "kaggle_datasets",
    "description": (
        "Baixa amostras do Kaggle, em especial a classe Burglary (arrombamento) do "
        "dataset odins0n/ucf-crime-dataset para memory/teste_cameras/. "
        "Gatilhos: 'baixar dataset de arrombamento do Kaggle', 'preparar amostra de invasão', /baixar_kaggle."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["download_burglary", "status", "setup_help"],
            },
            "dataset": {"type": "STRING"},
            "limit": {"type": "NUMBER"},
        },
        "required": [],
    },
    "handler": kaggle_datasets,
    "tier": "core",
    "risk": "review",
}
