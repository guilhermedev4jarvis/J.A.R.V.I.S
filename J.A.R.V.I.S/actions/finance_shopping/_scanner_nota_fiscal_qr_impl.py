"""Leitor e registrador de NFC-e integrado ao controle de gastos."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from core.outcome import done, failed

_BASE = Path(__file__).resolve().parents[2]
_RECEIPTS_LOG = _BASE / "memory" / "nfce_receipts.jsonl"


def _decode_qr_from_image(image_path: str) -> str:
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is not None:
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(img)
            return data.strip()
    except Exception:
        pass
    return ""


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    nfce_url = str(params.get("nfce_url") or "").strip()
    image_path = str(params.get("image_path") or "").strip()
    store = str(params.get("store") or "Estabelecimento NFC-e").strip()
    total_amount = float(params.get("total_amount") or 0.0)

    if not nfce_url and image_path:
        nfce_url = _decode_qr_from_image(image_path)

    if not nfce_url and total_amount <= 0:
        return failed("scanner_nota_fiscal_qr", "Informe nfce_url, image_path com QR Code valido ou total_amount.")

    chave_match = re.search(r"(\d{44})", nfce_url)
    chave_acesso = chave_match.group(1) if chave_match else ""

    record: Dict[str, Any] = {
        "ts": datetime.now().isoformat(),
        "store": store,
        "nfce_url": nfce_url,
        "chave_acesso": chave_acesso,
        "total_amount": total_amount,
    }
    _RECEIPTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _RECEIPTS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if total_amount > 0:
        try:
            from actions.finance_shopping import _controle_gastos_impl as cg
            if hasattr(cg, "run"):
                cg.run({"action": "add", "amount": total_amount, "description": f"NFC-e {store}"})
        except Exception:
            pass

    return done("scanner_nota_fiscal_qr", f"Nota fiscal de '{store}' registrada com sucesso.", record)