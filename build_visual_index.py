#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_visual_index.py
─────────────────────
Constrói índice de similaridade visual a partir do banco histórico (BDA).
Para cada obra com foto + artista identificado, calcula phash e salva em
visual_index.json.

Uso:
  python build_visual_index.py              # indexa tudo (pode demorar ~15 min)
  python build_visual_index.py --max 1000   # limita a 1000 obras (por lance)
  python build_visual_index.py --threads 12 # mais threads = mais rápido
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import imagehash
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DIR       = os.path.dirname(os.path.abspath(__file__))
BDA_FILE   = os.path.join(_DIR, "bolsadearte_db.json")
INDEX_FILE = os.path.join(_DIR, "visual_index.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0",
    "Accept": "image/*,*/*",
    "Referer": "https://www.bolsadearte.com/",
}


def _compute_hash(foto_url: str) -> str | None:
    """Baixa imagem e retorna phash string. None se falhar."""
    try:
        r = requests.get(foto_url, headers=HEADERS, timeout=12)
        if r.status_code != 200 or len(r.content) < 800:
            return None
        img = Image.open(BytesIO(r.content)).convert("RGB")
        # Usa phash (64 bits) — bom para composição/cores gerais
        return str(imagehash.phash(img, hash_size=8))
    except Exception:
        return None


def _processar(c: dict):
    """Processa um candidato: baixa foto, computa hash. Retorna (url_key, entry) ou None."""
    h = _compute_hash(c["foto_url"])
    if h is None:
        return None
    return c["url_key"], {
        "phash":       h,
        "artista":     c["artista"],
        "titulo":      c["titulo"],
        "tecnica":     c["tecnica"],
        "dimensoes":   c["dimensoes"],
        "maior_lance": c["maior_lance"],
        "casa":        c["casa"],
        "data_leilao": c["data_leilao"],
        "foto_url":    c["foto_url"],
        "url_key":     c["url_key"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max",       type=int,   default=0,  help="Máximo de obras (0=todas; prioriza por lance)")
    ap.add_argument("--threads",   type=int,   default=8,  help="Threads paralelas de download")
    ap.add_argument("--min-lance", type=float, default=0,  help="Só obras com lance >= este valor")
    ap.add_argument("--rebuild",   action="store_true",    help="Reconstrói do zero (ignora índice existente)")
    args = ap.parse_args()

    import os as _os
    SB_URL = _os.environ.get("SUPABASE_URL", "https://mzjyxqwdnlzmotqxgcqa.supabase.co")
    SB_KEY = _os.environ.get("SUPABASE_KEY", "")
    USE_SB = bool(SB_KEY)

    def _sb_headers():
        return {
            "apikey": SB_KEY,
            "Authorization": f"Bearer {SB_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def _sb_fetch_all_vi():
        rows, offset = [], 0
        while True:
            r = requests.get(f"{SB_URL}/rest/v1/visual_index?select=url_key",
                             headers=_sb_headers(),
                             params={"offset": offset, "limit": 1000}, timeout=30)
            batch = r.json() if r.status_code == 200 else []
            rows.extend(batch)
            if len(batch) < 1000: break
            offset += 1000
        return {r["url_key"] for r in rows}

    def _sb_fetch_bda():
        rows, offset = [], 0
        while True:
            r = requests.get(f"{SB_URL}/rest/v1/lotes?select=chave,artista,titulo,tecnica,dimensoes,maior_lance,casa,data_leilao,foto_url&fonte=eq.bda",
                             headers=_sb_headers(),
                             params={"offset": offset, "limit": 1000}, timeout=30)
            batch = r.json() if r.status_code == 200 else []
            rows.extend(batch)
            if len(batch) < 1000: break
            offset += 1000
        return rows

    def _sb_upsert_vi(rows_vi):
        url = f"{SB_URL}/rest/v1/visual_index"
        for i in range(0, len(rows_vi), 400):
            requests.post(url, headers=_sb_headers(), json=rows_vi[i:i+400], timeout=60)

    # Carrega índice existente para retomar (incremental)
    if USE_SB and not args.rebuild:
        index_keys = _sb_fetch_all_vi()
        index = {k: True for k in index_keys}  # só as chaves para checar duplicatas
        print(f"Índice Supabase: {len(index)} obras já indexadas")
    elif os.path.exists(INDEX_FILE) and not args.rebuild:
        with open(INDEX_FILE, encoding="utf-8") as f:
            index = json.load(f)
        print(f"Índice existente: {len(index)} obras já indexadas (use --rebuild para reconstruir)")
    else:
        index = {}
        print("Construindo índice do zero...")

    # Carrega BDA
    if USE_SB:
        print("Carregando BDA do Supabase...", end=" ", flush=True)
        bda_rows = _sb_fetch_bda()
        bda = {}
        for r in bda_rows:
            url_key = r["chave"].replace("bda|", "", 1)
            bda[url_key] = r
        print(f"{len(bda)} registros")
    else:
        print(f"Carregando {os.path.basename(BDA_FILE)}...", end=" ", flush=True)
        with open(BDA_FILE, encoding="utf-8") as f:
            bda = json.load(f)
        print(f"{len(bda)} registros")

    # Filtra candidatos válidos ainda não indexados
    candidatos = []
    for url_key, v in bda.items():
        if not isinstance(v, dict):
            continue
        if url_key in index:
            continue
        foto = v.get("foto_url", "").strip()
        if not foto:
            continue
        artista = v.get("artista", "").strip()
        if not artista:
            continue
        lance = float(v.get("maior_lance") or 0)
        if lance < args.min_lance:
            continue
        candidatos.append({
            "url_key":     url_key,
            "foto_url":    foto,
            "artista":     artista,
            "titulo":      (v.get("titulo") or "").strip(),
            "tecnica":     (v.get("tecnica") or "").strip(),
            "dimensoes":   (v.get("dimensoes") or "").strip(),
            "maior_lance": lance,
            "casa":        (v.get("casa") or "").strip(),
            "data_leilao": (v.get("data_leilao") or "").strip(),
        })

    # Prioriza obras com maior lance (mais valiosas primeiro)
    candidatos.sort(key=lambda x: x["maior_lance"], reverse=True)

    if args.max:
        candidatos = candidatos[:args.max]

    total = len(candidatos)
    print(f"A indexar: {total} obras novas | threads: {args.threads}")
    if total == 0:
        print("Nada a fazer — índice já está completo.")
        return

    ok = err = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futuros = {ex.submit(_processar, c): c for c in candidatos}
        for i, fut in enumerate(as_completed(futuros), 1):
            res = fut.result()
            if res:
                url_key, entry = res
                index[url_key] = entry
                ok += 1
            else:
                err += 1

            if i % 100 == 0 or i == total:
                elapsed = time.time() - t0
                eta = (elapsed / i) * (total - i) if i < total else 0
                pct = i * 100 // total
                print(f"  [{pct:3d}%] {i}/{total} — {ok} ok | {err} erros | "
                      f"{elapsed:.0f}s decorridos | ETA ~{eta:.0f}s")
                # Salva progressivamente a cada 100
                if USE_SB:
                    novas = [{"url_key": k, **v} for k, v in index.items()
                             if isinstance(v, dict)][-min(ok, 100):]
                    _sb_upsert_vi(novas)
                else:
                    with open(INDEX_FILE, "w", encoding="utf-8") as f:
                        json.dump(index, f, ensure_ascii=False)

    # Salva final
    if USE_SB:
        todas = [{"url_key": k, **v} for k, v in index.items() if isinstance(v, dict)]
        _sb_upsert_vi(todas)
    else:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  Concluído! {ok} obras indexadas ({err} falhas)")
    print(f"  Total no índice: {len(index)} obras")
    print(f"  {'Supabase' if USE_SB else INDEX_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
