"""Etapa 02 — limpeza: data/02_processed/ocr/ -> data/02_processed/clean/.

Uso: python scripts/02_clean.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # funciona mesmo sem pip install -e .

from jurismatch.pipeline_limpeza import main

if __name__ == "__main__":
    main()
