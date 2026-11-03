"""Etapa 05 — busca pela linha de comando.

Uso: python scripts/05_search.py "sua consulta" [--k 5] [--modo hibrido|denso|lexical]
     [--classe ADI|ADC] [--limiar 0.8] [--sem-rerank]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # funciona mesmo sem pip install -e .

from jurismatch.busca import main

if __name__ == "__main__":
    main()
