"""Action: local_doc_rag — read/summarize/search local documents (pdf/docx/txt/md)."""
from __future__ import annotations

from core.outcome import failed


def local_doc_rag(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._local_doc_rag_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("local_doc_rag", f"impl error: {e}")


TOOL = {
    "name": "local_doc_rag",
    "description": (
        "Read, summarize or search local documents (.pdf, .docx, .txt, .md) under "
        "sandbox-allowed paths. Use for 'resuma este PDF', 'o que diz o arquivo X', "
        "'procure Y no documento'. Never reads outside allowed roots; applies redaction."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "read | summarize | search",
                "enum": ["read", "summarize", "search"],
            },
            "path": {"type": "STRING", "description": "Absolute or user-relative file path"},
            "query": {"type": "STRING", "description": "Search query or question"},
        },
        "required": [],
    },
    "handler": local_doc_rag,
    "tier": "core",
    "risk": "safe",
}
