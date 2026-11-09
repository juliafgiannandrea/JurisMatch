"""Etapa 04 — indexação: data/03_chunks/chunks.parquet -> vectorstore/ (embeddings, FAISS, BM25).

Uso: python scripts/04_index.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # funciona mesmo sem pip install -e .

from jurismatch.indexar import main

if __name__ == "__main__":
    main()
