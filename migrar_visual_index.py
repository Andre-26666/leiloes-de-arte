#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migra visual_index.json para tabela Supabase."""

import json, os, requests, sys

SUPABASE_URL = "https://mzjyxqwdnlzmotqxgcqa.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_KEY:
    print("ERRO: defina SUPABASE_KEY")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_DIR, "visual_index.json"), encoding="utf-8") as f:
    idx = json.load(f)

rows = []
for url_key, v in idx.items():
    if not isinstance(v, dict) or not v.get("phash"):
        continue
    rows.append({
        "url_key":     url_key,
        "phash":       v.get("phash"),
        "artista":     v.get("artista") or None,
        "titulo":      v.get("titulo") or None,
        "tecnica":     v.get("tecnica") or None,
        "dimensoes":   v.get("dimensoes") or None,
        "maior_lance": v.get("maior_lance") or None,
        "casa":        v.get("casa") or None,
        "data_leilao": v.get("data_leilao") or None,
        "foto_url":    v.get("foto_url") or None,
    })

url = f"{SUPABASE_URL}/rest/v1/visual_index"
batch_size = 400
total = 0
for i in range(0, len(rows), batch_size):
    batch = rows[i:i+batch_size]
    r = requests.post(url, headers=HEADERS, json=batch, timeout=60)
    if r.status_code not in (200, 201):
        print(f"ERRO: {r.status_code} — {r.text[:200]}")
    else:
        total += len(batch)
        print(f"  {total}/{len(rows)} enviados...")

print(f"\n✅ visual_index: {len(rows)} registros migrados")
