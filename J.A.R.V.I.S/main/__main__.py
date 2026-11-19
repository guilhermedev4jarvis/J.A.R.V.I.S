"""python -m main"""
from __future__ import annotations
from core.preboot_gate import run_preboot_gate
run_preboot_gate()
from main.lifecycle import main
if __name__ == "__main__":
    main()
