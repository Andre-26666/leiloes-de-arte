#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_now.py — Sincroniza os JSONs locais com o Supabase.
Use após rodar o scraping local quando o GitHub Actions não pega os lotes.

Uso: python sync_now.py
"""
import json, os, ssl, sys, urllib.request
from collections import Counter

SB_URL = os.environ.get("SUPABASE_URL", "https://mzjyxqwdnlzmotqxgcqa.supabase.co")
SB_KEY = os.environ.get("SUPABASE_KEY", "")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

def _safe(v):
    if v is None: return None
    if isinstance(v, float) and v != v: return None
    return v

def _upsert(rows, label):
    total = 0
    for i in range(0, len(rows), 100):
        batch = rows[i:i+100]
        data = json.dumps(batch).encode()
        req = urllib.request.Request(
            f"{SB_URL}/rest/v1/lotes?on_conflict=chave",
            data=data, headers=HEADERS, method="POST"
        )
        try:
            with urllib.request.urlopen(req, context=ctx) as r:
                total += len(batch)
        except urllib.error.HTTPError as e:
            print(f"  ERRO batch {i//100+1}: {e.code} {e.read().decode()[:200]}")
    print(f"  {label}: {total} lotes sincronizados")
    return total

def sync_leiloesbr():
    path = os.path.join(os.path.dirname(__file__), "leiloesbr_db.json")
    if not os.path.exists(path):
        print("  leiloesbr_db.json não encontrado, pulando.")
        return
    with open(path, encoding="utf-8") as f:
        db = json.load(f)
    rows = []
    for k, v in db.items():
        if not isinstance(v, dict): continue
        rows.append({
            "chave":       f"leiloesbr|{k}",
            "fonte":       "leiloesbr",
            "artista":     _safe(v.get("artista")),
            "titulo":      _safe(v.get("titulo")),
            "tecnica":     _safe(v.get("tecnica")),
            "dimensoes":   _safe(v.get("dimensoes")),
            "ano":         _safe(v.get("ano")),
            "lance_base":  float(v.get("lance_base") or 0),
            "maior_lance": float(v.get("maior_lance") or 0),
            "num_lances":  int(v.get("num_lances") or 0),
            "data_leilao": _safe(v.get("data_leilao")),
            "casa":        _safe(v.get("casa")),
            "url_detalhe": _safe(v.get("url_detalhe")),
            "foto_url":    _safe(v.get("foto_url")),
            "em_leilao":   bool(v.get("em_leilao", True)),
            "ignorado":    bool(v.get("_ignorado", False)),
            "data_coleta": _safe(v.get("data_coleta")),
        })
    datas = Counter(str(r["data_leilao"] or "") for r in rows if r["em_leilao"])
    print(f"  Datas ativas: {dict(datas.most_common(5))}")
    _upsert(rows, "leiloesbr")

def main():
    print("=" * 50)
    print("  Sync local → Supabase")
    print("=" * 50)
    sync_leiloesbr()
    print("=" * 50)
    print("  Concluído! Abra a plataforma e clique ↺")
    print("=" * 50)

if __name__ == "__main__":
    main()
