#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
garimpo_visual_precompute.py
────────────────────────────
Pré-calcula resultados do Garimpo Visual e salva em `garimpo_resultados` no Supabase.

Roda via GitHub Actions após cada garimpo diário.
Lê lotes ativos com artista desconhecido, compara contra visual_index,
salva os similares encontrados para exibição instantânea na plataforma.

Uso:
  python garimpo_visual_precompute.py
  python garimpo_visual_precompute.py --max 200   # limita a 200 lotes
  python garimpo_visual_precompute.py --rebuild   # recalcula tudo (ignora já processados)
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO

import imagehash
import requests
from PIL import Image

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


# ── Regex artista desconhecido (idêntico ao plataforma.py) ───────────────────
_RE_DESC = re.compile(
    r'\b(n[aã]o\s+identificad|desconhecid|an[oô]nim|atribu[ií]d|attr\b|'
    r'sem\s+autoria|incerto|s\.a\b|s/a\b|unknown)\b',
    re.IGNORECASE,
)


def _eh_desconhecido(artista: str) -> bool:
    art = str(artista or "").strip()
    return not art or bool(_RE_DESC.search(art))


# ── Supabase helpers ─────────────────────────────────────────────────────────

def _sb_fetch_all(table: str, select: str = "*", filters: dict | None = None) -> list:
    rows, offset = [], 0
    while True:
        params = {"offset": offset, "limit": 1000, "select": select}
        if filters:
            params.update(filters)
        r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=_headers(),
                         params=params, timeout=30)
        batch = r.json() if r.status_code == 200 else []
        if not isinstance(batch, list):
            print(f"  AVISO: resposta inesperada de {table}: {batch}")
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def _sb_upsert(table: str, rows: list) -> None:
    url = f"{SB_URL}/rest/v1/{table}"
    for i in range(0, len(rows), 200):
        chunk = rows[i:i+200]
        r = requests.post(url, headers=_headers(), json=chunk, timeout=60)
        if r.status_code not in (200, 201):
            print(f"  AVISO upsert {table}: {r.status_code} {r.text[:200]}")


def _sb_get_processed_urls() -> set:
    """Retorna set de url_detalhe já em garimpo_resultados."""
    rows = _sb_fetch_all("garimpo_resultados", select="url_detalhe")
    return {r["url_detalhe"] for r in rows if r.get("url_detalhe")}


# ── Cálculo de phash ─────────────────────────────────────────────────────────

_IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0",
    "Accept": "image/*,*/*",
}


def _compute_hash(foto_url: str):
    """Baixa imagem e retorna imagehash.phash ou None."""
    try:
        r = requests.get(foto_url, headers=_IMG_HEADERS, timeout=15)
        if r.status_code != 200 or len(r.content) < 500:
            return None
        return imagehash.phash(Image.open(BytesIO(r.content)).convert("RGB"), hash_size=12)
    except Exception:
        return None


# ── Busca similares no índice ────────────────────────────────────────────────

def _buscar_similares(query_hash, index: list, top_n: int = 5, max_dist: int = 45) -> list:
    hash_bits = query_hash.hash.size  # 144 para hash_size=12
    results = []
    for entry in index:
        try:
            ref_hash = imagehash.hex_to_hash(entry["phash"])
            if ref_hash.hash.size != hash_bits:
                continue  # ignora entradas com hash de tamanho diferente (índice antigo)
            dist = query_hash - ref_hash
            if dist <= max_dist:
                sim = round(max(0, 100 - dist * 100 / hash_bits))
                results.append({
                    "artista":     entry.get("artista", ""),
                    "titulo":      entry.get("titulo", ""),
                    "tecnica":     entry.get("tecnica", ""),
                    "dimensoes":   entry.get("dimensoes", ""),
                    "maior_lance": entry.get("maior_lance", 0),
                    "casa":        entry.get("casa", ""),
                    "data_leilao": entry.get("data_leilao", ""),
                    "foto_url":    entry.get("foto_url", ""),
                    "url_key":     entry.get("url_key", ""),
                    "similarity":  sim,
                    "dist":        dist,
                })
        except Exception:
            continue
    results.sort(key=lambda x: x["dist"])
    return results[:top_n]


# ── Processamento de um lote ─────────────────────────────────────────────────

def _processar_lote(lote: dict, index: list, max_dist: int = 45) -> dict | None:
    """Processa um lote: baixa foto, calcula phash, busca similares. Retorna linha para upsert ou None."""
    foto = (lote.get("foto_url") or "").strip()
    if not foto:
        return None

    query_hash = _compute_hash(foto)
    if query_hash is None:
        return None

    similares = _buscar_similares(query_hash, index, top_n=5, max_dist=max_dist)

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "url_detalhe": lote.get("url_detalhe", ""),
        "foto_url":    foto,
        "artista":     (lote.get("artista") or "").strip(),
        "titulo":      (lote.get("titulo") or "").strip(),
        "tecnica":     (lote.get("tecnica") or "").strip(),
        "dimensoes":   (lote.get("dimensoes") or "").strip(),
        "lance_base":  float(lote.get("lance_base") or 0),
        "casa":        (lote.get("casa") or "").strip(),
        "data_leilao": (lote.get("data_leilao") or "").strip(),
        "similares":   similares,   # jsonb — lista de dicts
        "atualizado":  agora,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max",     type=int, default=0,   help="Máximo de lotes a processar (0=todos)")
    ap.add_argument("--threads", type=int, default=6,   help="Threads paralelas")
    ap.add_argument("--max-dist",type=int, default=45,  help="Distância máxima phash (0-144 para hash_size=12)")
    ap.add_argument("--rebuild", action="store_true",   help="Recalcula todos (ignora já processados)")
    args = ap.parse_args()

    print("=" * 60)
    print("  Garimpo Visual — Pré-computação")
    print("=" * 60)

    # 1. Carrega índice visual
    print("Carregando visual_index do Supabase...", end=" ", flush=True)
    index = _sb_fetch_all("visual_index", select="url_key,phash,artista,titulo,tecnica,dimensoes,maior_lance,casa,data_leilao,foto_url")
    index = [r for r in index if r.get("phash")]
    print(f"{len(index)} obras indexadas")

    if not index:
        print("ERRO: índice visual vazio — execute build_visual_index.py primeiro.")
        sys.exit(1)

    # 2. Carrega lotes ativos
    print("Carregando lotes ativos do Supabase...", end=" ", flush=True)
    lotes_rows = _sb_fetch_all(
        "lotes",
        select="chave,artista,titulo,tecnica,dimensoes,lance_base,casa,data_leilao,foto_url,url_detalhe,status",
        filters={"status": "eq.ativo"},
    )
    print(f"{len(lotes_rows)} lotes ativos")

    # 3. Filtra desconhecidos com foto
    candidatos = [
        r for r in lotes_rows
        if _eh_desconhecido(r.get("artista", ""))
        and (r.get("foto_url") or "").strip()
        and (r.get("url_detalhe") or "").strip()
    ]
    print(f"Lotes com artista desconhecido e foto: {len(candidatos)}")

    # 4. Remove já processados (incremental)
    if not args.rebuild:
        print("Carregando URLs já processadas...", end=" ", flush=True)
        ja_processados = _sb_get_processed_urls()
        print(f"{len(ja_processados)} já processados")
        candidatos = [c for c in candidatos if c.get("url_detalhe") not in ja_processados]
        print(f"Novos a processar: {len(candidatos)}")
    else:
        print("Modo rebuild — recalculando tudo")

    # Prioriza por lance_base desc
    candidatos.sort(key=lambda x: float(x.get("lance_base") or 0), reverse=True)

    if args.max:
        candidatos = candidatos[:args.max]

    total = len(candidatos)
    if total == 0:
        print("\nNada a processar — garimpo visual já está atualizado.")
        return

    print(f"\nProcessando {total} lotes | threads: {args.threads}")
    print("-" * 60)

    ok = err = sem_similar = 0
    t0 = time.time()
    buffer = []

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futuros = {ex.submit(_processar_lote, c, index, args.max_dist): c for c in candidatos}

        for i, fut in enumerate(as_completed(futuros), 1):
            res = fut.result()
            if res is None:
                err += 1
            elif not res["similares"]:
                # Salva mesmo sem similares (para não reprocessar)
                sem_similar += 1
                buffer.append(res)
                ok += 1
            else:
                buffer.append(res)
                ok += 1

            # Salva a cada 50 lotes
            if len(buffer) >= 50 or i == total:
                if buffer:
                    _sb_upsert("garimpo_resultados", buffer)
                    buffer = []

            if i % 25 == 0 or i == total:
                elapsed = time.time() - t0
                eta = (elapsed / i) * (total - i) if i < total else 0
                pct = i * 100 // total
                print(f"  [{pct:3d}%] {i}/{total} — {ok} ok | {sem_similar} sem similar | {err} erros | ETA ~{eta:.0f}s")

    print()
    print("=" * 60)
    print(f"  Concluído! {ok} lotes processados ({err} falhas)")
    print(f"  Com similares encontrados: {ok - sem_similar}")
    print(f"  Sem similares: {sem_similar}")
    print(f"  Tempo total: {time.time() - t0:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
