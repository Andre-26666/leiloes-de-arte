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
import base64
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO

import imagehash
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
            # Se falhou por coluna inexistente (assinatura_ocr), tenta sem ela
            if "assinatura_ocr" in (r.text or ""):
                chunk2 = [{k: v for k, v in row.items() if k != "assinatura_ocr"} for row in chunk]
                r2 = requests.post(url, headers=_headers(), json=chunk2, timeout=60)
                if r2.status_code not in (200, 201):
                    print(f"  AVISO upsert {table}: {r2.status_code} {r2.text[:200]}")
                else:
                    print(f"  AVISO: coluna assinatura_ocr não existe — adicioná-la no Supabase")
            else:
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


def _download_img(foto_url: str):
    """Baixa imagem e retorna objeto PIL Image ou None."""
    try:
        r = requests.get(foto_url, headers=_IMG_HEADERS, timeout=15)
        if r.status_code != 200 or len(r.content) < 500:
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def _compute_hash(img):
    """Recebe PIL Image e retorna phash ou None."""
    try:
        return imagehash.phash(img, hash_size=12)
    except Exception:
        return None


# ── OCR de assinatura ─────────────────────────────────────────────────────────

def _extrair_assinatura(img) -> str:
    """Tenta extrair texto de assinatura da pintura via OCR.
    Recorta o terço inferior da imagem onde assinaturas costumam estar."""
    try:
        import pytesseract
        from PIL import ImageOps, ImageFilter, ImageEnhance

        w, h = img.size
        # Regiões candidatas: canto inferior esquerdo, centro-baixo, canto inferior direito
        regioes = [
            img.crop((0,           int(h * 0.72), int(w * 0.45), h)),   # baixo-esquerdo
            img.crop((int(w * 0.55), int(h * 0.72), w,           h)),   # baixo-direito
            img.crop((0,           int(h * 0.60), w,             h)),   # faixa inferior
        ]

        textos = set()
        for reg in regioes:
            # Pré-processamento: escala 3×, contraste alto, P&B
            r = reg.convert("L")
            r = r.resize((r.width * 3, r.height * 3), Image.LANCZOS)
            r = ImageEnhance.Contrast(r).enhance(2.5)
            r = ImageOps.autocontrast(r, cutoff=2)
            r = r.filter(ImageFilter.SHARPEN)

            txt = pytesseract.image_to_string(
                r, config="--psm 11 --oem 3 -l por+eng"
            ).strip()
            for linha in txt.split("\n"):
                linha = linha.strip()
                # Filtra ruído: só linhas com 3-60 chars e ao menos 1 letra
                if 3 <= len(linha) <= 60 and any(c.isalpha() for c in linha):
                    textos.add(linha)

        return " | ".join(sorted(textos)[:4]) if textos else ""
    except Exception:
        return ""


# ── CLIP helpers ─────────────────────────────────────────────────────────────

def _b64_to_emb(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=np.float32)


def _load_clip_model():
    """Tenta carregar modelo CLIP. Retorna (model, processor) ou (None, None)."""
    try:
        from transformers import CLIPProcessor, CLIPModel
        import torch
        print("  Carregando modelo CLIP...", end=" ", flush=True)
        model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        model.eval()
        print("OK")
        return model, processor
    except Exception as e:
        print(f"  CLIP não disponível ({e}) — usando só phash")
        return None, None


def _build_clip_matrix(index: list) -> tuple:
    """Constrói matriz numpy com todos os embeddings CLIP do índice.
    Retorna (matrix NxD, keys list) ou (None, None) se não houver embeddings."""
    entries = [(r["url_key"], _b64_to_emb(r["clip_embedding"]))
               for r in index if r.get("clip_embedding")]
    if not entries:
        return None, None
    keys   = [e[0] for e in entries]
    matrix = np.stack([e[1] for e in entries])  # (N, 512)
    return matrix, keys


def _get_clip_embedding(img, model, processor, lock: threading.Lock) -> np.ndarray | None:
    """Extrai embedding CLIP normalizado de uma PIL Image."""
    try:
        import torch
        with lock:
            with torch.no_grad():
                inputs   = processor(images=img, return_tensors="pt")
                features = model.get_image_features(**inputs)
                emb      = features[0].numpy()
        norm = np.linalg.norm(emb)
        return emb / norm if norm > 0 else None
    except Exception:
        return None


def _buscar_clip_similares(query_emb: np.ndarray, matrix: np.ndarray,
                            keys: list, index_dict: dict,
                            top_n: int = 5, min_sim: float = 0.72) -> list:
    """Busca similares por cosine similarity CLIP. min_sim: 0-1."""
    sims    = matrix @ query_emb          # produto escalar (já normalizado = cosine)
    indices = np.argsort(sims)[::-1]      # ordem decrescente
    results = []
    for idx in indices:
        sim_val = float(sims[idx])
        if sim_val < min_sim:
            break
        uk    = keys[idx]
        entry = index_dict.get(uk, {})
        results.append({
            "artista":     entry.get("artista", ""),
            "titulo":      entry.get("titulo", ""),
            "tecnica":     entry.get("tecnica", ""),
            "dimensoes":   entry.get("dimensoes", ""),
            "maior_lance": entry.get("maior_lance", 0),
            "casa":        entry.get("casa", ""),
            "data_leilao": entry.get("data_leilao", ""),
            "foto_url":    entry.get("foto_url", ""),
            "url_key":     uk,
            "similarity":  round(sim_val * 100),
            "method":      "clip",
        })
        if len(results) >= top_n:
            break
    return results


# ── Busca similares por phash ─────────────────────────────────────────────────

def _buscar_similares(query_hash, index: list, top_n: int = 5, max_dist: int = 45) -> list:
    hash_bits = query_hash.hash.size  # 144 para hash_size=12
    results = []
    for entry in index:
        try:
            ref_hash = imagehash.hex_to_hash(entry["phash"])
            if ref_hash.hash.size != hash_bits:
                continue
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
                    "method":      "phash",
                })
        except Exception:
            continue
    results.sort(key=lambda x: x["dist"])
    return results[:top_n]


def _merge_similares(clip_sims: list, phash_sims: list, top_n: int = 5) -> list:
    """Combina CLIP e phash: CLIP tem prioridade. Evita duplicatas por url_key."""
    seen  = set()
    final = []
    for s in clip_sims + phash_sims:
        uk = s.get("url_key", "")
        if uk and uk not in seen:
            seen.add(uk)
            final.append(s)
        if len(final) >= top_n:
            break
    return final


# ── Processamento de um lote ─────────────────────────────────────────────────

# Estado CLIP compartilhado (inicializado em main se modelo disponível)
_CLIP_MODEL     = None
_CLIP_PROCESSOR = None
_CLIP_MATRIX    = None   # np.ndarray (N, 512)
_CLIP_KEYS      = None   # list[str] de url_keys
_CLIP_IDX_DICT  = None   # dict url_key → entry (para montar resultado)
_CLIP_LOCK      = threading.Lock()


def _processar_lote(lote: dict, index: list, max_dist: int = 45) -> dict | None:
    """Processa um lote: baixa foto, calcula phash + CLIP, busca similares, extrai OCR."""
    foto = (lote.get("foto_url") or "").strip()
    if not foto:
        return None

    img = _download_img(foto)
    if img is None:
        return None

    query_hash = _compute_hash(img)
    if query_hash is None:
        return None

    # Similares por phash
    phash_sims = _buscar_similares(query_hash, index, top_n=5, max_dist=max_dist)

    # Similares por CLIP (se índice disponível)
    clip_sims = []
    if _CLIP_MODEL is not None and _CLIP_MATRIX is not None:
        emb = _get_clip_embedding(img, _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_LOCK)
        if emb is not None:
            clip_sims = _buscar_clip_similares(
                emb, _CLIP_MATRIX, _CLIP_KEYS, _CLIP_IDX_DICT, top_n=5
            )

    # CLIP tem prioridade; phash preenche o que falta
    similares      = _merge_similares(clip_sims, phash_sims, top_n=5)
    assinatura_ocr = _extrair_assinatura(img)
    agora          = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "url_detalhe":    lote.get("url_detalhe", ""),
        "foto_url":       foto,
        "artista":        (lote.get("artista") or "").strip(),
        "titulo":         (lote.get("titulo") or "").strip(),
        "tecnica":        (lote.get("tecnica") or "").strip(),
        "dimensoes":      (lote.get("dimensoes") or "").strip(),
        "lance_base":     float(lote.get("lance_base") or 0),
        "casa":           (lote.get("casa") or "").strip(),
        "data_leilao":    (lote.get("data_leilao") or "").strip(),
        "similares":      similares,
        "assinatura_ocr": assinatura_ocr,
        "atualizado":     agora,
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

    # 1. Tenta carregar modelo CLIP
    global _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_MATRIX, _CLIP_KEYS, _CLIP_IDX_DICT
    _CLIP_MODEL, _CLIP_PROCESSOR = _load_clip_model()

    # 2. Carrega índice visual (com clip_embedding se disponível)
    print("Carregando visual_index do Supabase...", end=" ", flush=True)
    index = _sb_fetch_all(
        "visual_index",
        select="url_key,phash,artista,titulo,tecnica,dimensoes,maior_lance,"
               "casa,data_leilao,foto_url,clip_embedding"
    )
    index = [r for r in index if r.get("phash")]
    print(f"{len(index)} obras indexadas")

    # Constrói matriz CLIP para busca vetorial rápida
    if _CLIP_MODEL is not None:
        _CLIP_MATRIX, _CLIP_KEYS = _build_clip_matrix(index)
        _CLIP_IDX_DICT = {r["url_key"]: r for r in index}
        n_clip = len(_CLIP_KEYS) if _CLIP_KEYS else 0
        print(f"  Matriz CLIP: {n_clip}/{len(index)} obras com embedding")

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
