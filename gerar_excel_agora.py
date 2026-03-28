#!/usr/bin/env python3
"""Gera o Excel a partir do DB existente, sem fazer scraping.
Salva como catalogo_pinturas_DDMM.xlsx (ex: catalogo_pinturas_2503.xlsx)."""
import sys, os, json
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import importlib.util
spec = importlib.util.spec_from_file_location(
    "catalogo_leiloesbr",
    os.path.join(_DIR, "catalogo_leiloesbr.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with open(os.path.join(_DIR, "leiloesbr_db.json"), "r", encoding="utf-8") as f:
    db = json.load(f)

print(f"DB carregado: {len(db)} lotes")

# Salva com nome da data de hoje
hoje = date.today().strftime("%d%m")
from datetime import datetime
hora = datetime.now().strftime("%H%M")
nome = os.path.join(_DIR, f"catalogo_pinturas_{hoje}_{hora}.xlsx")
mod.OUTPUT_XLSX = nome
mod.save_excel(db)
print(f"Excel gerado: {nome}")
