#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arquivar_lotes.py
─────────────────
Arquiva lotes cujo leilão já passou: muda em_leilao=True → False no Supabase.
Assim eles saem de "Em Leilão Agora" e entram em "Histórico de Preços".

Roda via GitHub Actions logo antes de cada garimpo.
"""

import os
import re
import sys
from datetime import date, datetime

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SB_URL = os.environ.get("SUPABASE_URL", "https://mzjyxqwdnlzmotqxgcqa.supabase.co")
SB_KEY = os.environ.get("SUPABASE_KEY", "")

if not SB_KEY:
    print("ERRO: SUPABASE_KEY não definida.")
    sys.exit(1)


def _headers():
    return {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def _parse_data(data_str: str):
    """Converte 'dd/mm/yyyy' → date. Retorna None se inválida."""
    if not data_str:
        return None
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', str(data_str))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _sb_fetch_ativos() -> list:
    """Busca todos os lotes com em_leilao=True."""
    rows, offset = [], 0
    while True:
        r = requests.get(
            f"{SB_URL}/rest/v1/lotes",
            headers=_headers(),
            params={
                "select": "chave,data_leilao",
                "em_leilao": "eq.true",
                "offset": offset,
                "limit": 1000,
            },
            timeout=30,
        )
        batch = r.json() if r.status_code == 200 else []
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def _sb_arquivar(chaves: list[str]) -> int:
    """Atualiza em_leilao=False para as chaves fornecidas em batches."""
    if not chaves:
        return 0
    url = f"{SB_URL}/rest/v1/lotes"
    total = 0
    batch_size = 200
    for i in range(0, len(chaves), batch_size):
        batch = chaves[i:i + batch_size]
        # PATCH com filtro chave=in.(...)
        chaves_str = "(" + ",".join(f'"{c}"' if "," in c else c for c in batch) + ")"
        r = requests.patch(
            url,
            headers={**_headers(), "Prefer": "return=minimal"},
            params={"chave": f"in.{chaves_str}"},
            json={"em_leilao": False, "status": "arquivado"},
            timeout=60,
        )
        if r.status_code in (200, 204):
            total += len(batch)
        else:
            print(f"  AVISO patch: {r.status_code} {r.text[:200]}")
    return total


def main():
    hoje = date.today()
    print("=" * 55)
    print(f"  Arquivamento de lotes — {hoje.strftime('%d/%m/%Y')}")
    print("=" * 55)

    print("Buscando lotes ativos no Supabase...", end=" ", flush=True)
    ativos = _sb_fetch_ativos()
    print(f"{len(ativos)} encontrados")

    # Filtra os que têm data passada
    para_arquivar = []
    sem_data = 0
    for row in ativos:
        dt = _parse_data(row.get("data_leilao", ""))
        if dt is None:
            sem_data += 1
            continue
        if dt < hoje:
            para_arquivar.append(row["chave"])

    print(f"  Com data passada: {len(para_arquivar)}")
    print(f"  Sem data (mantidos ativos): {sem_data}")

    if not para_arquivar:
        print("\nNenhum lote para arquivar.")
        return

    print(f"\nArquivando {len(para_arquivar)} lotes...", end=" ", flush=True)
    arquivados = _sb_arquivar(para_arquivar)
    print(f"{arquivados} atualizados")

    print("=" * 55)
    print(f"  Concluído! {arquivados} lotes → Histórico de Preços")
    print("=" * 55)


if __name__ == "__main__":
    main()
