"""Etapa 03 — chunking: data/02_processed/clean/ -> data/03_chunks/ e metadata/documentos.csv.

Uso: python scripts/03_chunk.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # funciona mesmo sem pip install -e .

from jurismatch.pipeline_chunks import main

if __name__ == "__main__":
    main()
