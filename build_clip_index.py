#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_clip_index.py
───────────────────
Extrai embeddings CLIP (512-dim) das obras históricas indexadas e salva
em visual_index.clip_embedding no Supabase.

O CLIP (Contrastive Language-Image Pretraining) entende estilo, paleta e
composição — bem melhor que phash para reconhecer o mesmo artista em fotos
diferentes da mesma obra ou de obras com estilo semelhante.

Uso:
  python build_clip_index.py               # processa até 400 obras novas
  python build_clip_index.py --max 2000    # até 2000 obras
  python build_clip_index.py --rebuild     # reconstrói tudo do zero
  python build_clip_index.py --threads 4   # threads de download
"""

import argparse
import base64
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import numpy as np
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


def _sb_fetch_all(table, select, filters=None):
    rows, off = [], 0
    while True:
        p = {"select": select, "limit": 1000, "offset": off}
        if filters:
            p.update(filters)
        r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=_headers(),
                         params=p, timeout=30)
        b = r.json() if r.status_code == 200 else []
        if not isinstance(b, list):
            print(f"  AVISO fetch: {b}")
            break
        rows.extend(b)
        if len(b) < 1000:
            break
        off += 1000
    return rows


def _sb_upsert(table, rows):
    url = f"{SB_URL}/rest/v1/{table}"
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        r = requests.post(url, headers=_headers(), json=chunk, timeout=60)
        if r.status_code not in (200, 201):
            # Verifica se coluna não existe ainda
            if "clip_embedding" in (r.text or ""):
                print("\n" + "!"*60)
                print("  COLUNA FALTANDO — execute no Supabase SQL Editor:")
                print("  ALTER TABLE visual_index")
                print("    ADD COLUMN IF NOT EXISTS clip_embedding text;")
                print("!"*60 + "\n")
            else:
                print(f"  AVISO upsert: {r.status_code} {r.text[:200]}")


# ── Encoding do embedding (float32 → base64 text) ───────────────────────────

def emb_to_b64(emb: np.ndarray) -> str:
    """Converte vetor float32 para string base64 (armazenamento compacto)."""
    return base64.b64encode(emb.astype(np.float32).tobytes()).decode()


def b64_to_emb(s: str) -> np.ndarray:
    """Converte string base64 de volta para vetor float32."""
    return np.frombuffer(base64.b64decode(s), dtype=np.float32)


# ── Download de imagem ────────────────────────────────────────────────────────

_IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0",
    "Accept": "image/*,*/*",
}


def _download_img(url: str):
    try:
        r = requests.get(url, headers=_IMG_HEADERS, timeout=15)
        if r.status_code != 200 or len(r.content) < 500:
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


# ── Extração de embedding CLIP ────────────────────────────────────────────────

def _load_clip():
    """Carrega modelo CLIP. Retorna (model, processor) ou lança exceção."""
    try:
        from transformers import CLIPProcessor, CLIPModel
        import torch
        print("  Baixando/carregando openai/clip-vit-base-patch32...", flush=True)
        model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        model.eval()
        return model, processor
    except ImportError:
        print("ERRO: instale as dependências:")
        print("  pip install transformers torch --extra-index-url "
              "https://download.pytorch.org/whl/cpu")
        sys.exit(1)


def _get_embedding(img: Image.Image, model, processor, lock: threading.Lock) -> np.ndarray | None:
    """Extrai embedding CLIP normalizado (512-dim) de uma imagem PIL."""
    try:
        import torch
        with lock:
            with torch.no_grad():
                inputs   = processor(images=img, return_tensors="pt")
                features = model.get_image_features(**inputs)
                emb      = features[0].numpy()
        # Normaliza para cosine similarity
        norm = np.linalg.norm(emb)
        if norm == 0:
            return None
        return emb / norm
    except Exception:
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max",     type=int, default=400, help="Máx obras por execução (0=tudo)")
    ap.add_argument("--threads", type=int, default=4,   help="Threads de download paralelo")
    ap.add_argument("--rebuild", action="store_true",   help="Reconstrói tudo do zero")
    args = ap.parse_args()

    print("=" * 60)
    print("  Build CLIP Index")
    print("=" * 60)

    # Carrega modelo CLIP
    t0_model = time.time()
    model, processor = _load_clip()
    print(f"  Modelo pronto em {time.time()-t0_model:.1f}s")
    clip_lock = threading.Lock()

    # Carrega visual_index
    print("\nCarregando visual_index...", end=" ", flush=True)
    index_rows = _sb_fetch_all(
        "visual_index",
        "url_key,foto_url,artista,titulo,tecnica,dimensoes,maior_lance,"
        "casa,data_leilao,phash,clip_embedding"
    )
    print(f"{len(index_rows)} entradas")

    if args.rebuild:
        candidatos = [r for r in index_rows if r.get("foto_url") and r.get("artista")]
    else:
        candidatos = [r for r in index_rows
                      if r.get("foto_url") and r.get("artista")
                      and not r.get("clip_embedding")]

    # Prioriza obras com maior lance
    candidatos.sort(key=lambda x: float(x.get("maior_lance") or 0), reverse=True)

    if args.max:
        candidatos = candidatos[:args.max]

    com_emb   = sum(1 for r in index_rows if r.get("clip_embedding"))
    print(f"  Já com embedding CLIP: {com_emb} | A processar: {len(candidatos)}")

    total = len(candidatos)
    if total == 0:
        print("\nÍndice CLIP já está completo.")
        return

    print(f"\nProcessando {total} obras | threads download: {args.threads}")
    print("-" * 60)

    # ── Fase 1: download paralelo das imagens ────────────────────────────────
    print("Fase 1/2 — Download de imagens...")
    imgs: dict[str, Image.Image] = {}
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futuros = {ex.submit(_download_img, c["foto_url"]): c["url_key"]
                   for c in candidatos}
        for n, fut in enumerate(as_completed(futuros), 1):
            uk  = futuros[fut]
            img = fut.result()
            if img:
                imgs[uk] = img
            if n % 100 == 0 or n == total:
                print(f"  {n}/{total} baixadas ({len(imgs)} ok)")

    # ── Fase 2: extração CLIP (sequencial por segurança) ────────────────────
    print(f"\nFase 2/2 — Extração CLIP ({len(imgs)} imagens)...")
    t0 = time.time()
    ok = err = 0
    buffer = []

    for i, c in enumerate(candidatos, 1):
        img = imgs.get(c["url_key"])
        if img is None:
            err += 1
        else:
            emb = _get_embedding(img, model, processor, clip_lock)
            if emb is None:
                err += 1
            else:
                buffer.append({
                    "url_key":        c["url_key"],
                    "clip_embedding": emb_to_b64(emb),
                    "phash":          c.get("phash") or "",
                    "artista":        c.get("artista") or "",
                    "titulo":         c.get("titulo") or "",
                    "tecnica":        c.get("tecnica") or "",
                    "dimensoes":      c.get("dimensoes") or "",
                    "maior_lance":    c.get("maior_lance") or 0,
                    "casa":           c.get("casa") or "",
                    "data_leilao":    c.get("data_leilao") or "",
                    "foto_url":       c.get("foto_url") or "",
                })
                ok += 1

        if len(buffer) >= 50 or i == total:
            if buffer:
                _sb_upsert("visual_index", buffer)
                buffer = []

        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            eta     = (elapsed / i) * (total - i) if i < total else 0
            pct     = i * 100 // total
            print(f"  [{pct:3d}%] {i}/{total} — {ok} ok | {err} erros | ETA ~{eta:.0f}s")

    print()
    print("=" * 60)
    print(f"  Concluído! {ok} embeddings CLIP gerados ({err} falhas)")
    print(f"  Total no índice CLIP: {com_emb + ok}")
    print(f"  Tempo: {time.time()-t0:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
