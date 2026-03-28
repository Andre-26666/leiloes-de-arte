#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper de sincronização com Supabase.
Importado pelos scripts de coleta para enviar dados ao banco na nuvem.
"""

import os
import requests as _requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://mzjyxqwdnlzmotqxgcqa.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

def _safe(v):
    if v is None or v == "":
        return None
    if isinstance(v, float) and (v != v or abs(v) == float('inf')):
        return None
    return v

def enabled():
    return bool(SUPABASE_KEY)

def upsert_raw(table, rows, batch_size=400):
    """Envia rows para tabela via REST. Retorna total enviado."""
    if not rows or not SUPABASE_KEY:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        r = _requests.post(url, headers=_HEADERS, json=batch, timeout=60)
        if r.status_code not in (200, 201):
            print(f"  [supabase] ERRO {r.status_code}: {r.text[:200]}")
        else:
            total += len(batch)
    return total

def sync_leiloesbr(db: dict):
    """Sincroniza leiloesbr_db com Supabase."""
    if not enabled():
        return
    rows = []
    for k, v in db.items():
        if not isinstance(v, dict):
            continue
        rows.append({
            "chave":       f"leiloesbr|{k}",
            "fonte":       "leiloesbr",
            "artista":     _safe(v.get("artista")),
            "titulo":      _safe(v.get("titulo")),
            "tecnica":     _safe(v.get("tecnica")),
            "dimensoes":   _safe(v.get("dimensoes")),
            "ano":         _safe(v.get("ano")),
            "lance_base":  _safe(v.get("lance_base")),
            "maior_lance": _safe(v.get("maior_lance")),
            "num_lances":  _safe(v.get("num_lances")),
            "data_leilao": _safe(v.get("data_leilao")),
            "casa":        _safe(v.get("casa")),
            "url_detalhe": _safe(v.get("url_detalhe")),
            "foto_url":    _safe(v.get("foto_url")),
            "em_leilao":   bool(v.get("em_leilao", True)),
            "ignorado":    bool(v.get("_ignorado", False)),
            "data_coleta": _safe(v.get("data_coleta")),
        })
    n = upsert_raw("lotes", rows)
    print(f"  [supabase] leiloesbr: {n}/{len(rows)} registros sincronizados")

def sync_bda(db: dict):
    """Sincroniza bolsadearte_db com Supabase."""
    if not enabled():
        return
    rows = []
    for k, v in db.items():
        if not isinstance(v, dict) or not v.get("artista"):
            continue
        rows.append({
            "chave":          f"bda|{k}",
            "fonte":          "bda",
            "artista":        _safe(v.get("artista")),
            "titulo":         _safe(v.get("titulo")),
            "tecnica":        _safe(v.get("tecnica")),
            "dimensoes":      _safe(v.get("dimensoes")),
            "ano":            _safe(v.get("ano")),
            "lance_base":     _safe(v.get("lance_base")),
            "maior_lance":    _safe(v.get("maior_lance")),
            "num_lances":     _safe(v.get("num_lances")),
            "estimativa_min": _safe(v.get("estimativa_min")),
            "estimativa_max": _safe(v.get("estimativa_max")),
            "data_leilao":    _safe(v.get("data_leilao")),
            "casa":           _safe(v.get("casa")),
            "url_detalhe":    _safe(v.get("url_detalhe")),
            "foto_url":       _safe(v.get("foto_url")),
            "assinatura":     _safe(v.get("assinatura")),
            "em_leilao":      False,
            "data_coleta":    _safe(v.get("data_coleta")),
        })
    n = upsert_raw("lotes", rows)
    print(f"  [supabase] bda: {n}/{len(rows)} registros sincronizados")

def sync_cda(db: dict):
    """Sincroniza cda_db com Supabase."""
    if not enabled():
        return
    rows = []
    for k, v in db.items():
        if not isinstance(v, dict) or not v.get("artista"):
            continue
        rows.append({
            "chave":         f"cda|{k}",
            "fonte":         "cda",
            "artista":       _safe(v.get("artista")),
            "titulo":        _safe(v.get("titulo")),
            "tecnica":       _safe(v.get("tecnica")),
            "dimensoes":     _safe(v.get("dimensoes")),
            "ano":           _safe(v.get("ano")),
            "lance_base":    _safe(v.get("lance_base")),
            "maior_lance":   _safe(v.get("maior_lance")),
            "num_lances":    _safe(v.get("num_lances")),
            "casa":          _safe(v.get("casa")),
            "url_detalhe":   _safe(v.get("url_detalhe")),
            "foto_url":      _safe(v.get("foto_url")),
            "assinatura":    _safe(v.get("assinatura")),
            "status":        _safe(v.get("status")),
            "descricao":     _safe(v.get("descricao")),
            "em_leilao":     False,
            "data_coleta":   _safe(v.get("data_coleta")),
            "fonte_url":     _safe(v.get("fonte_url")),
            "data_pesquisa": _safe(v.get("data_pesquisa")),
        })
    n = upsert_raw("lotes", rows)
    print(f"  [supabase] cda: {n}/{len(rows)} registros sincronizados")

def sync_tableau(lotes: list):
    """Sincroniza tableau_db com Supabase."""
    if not enabled():
        return
    rows = []
    for i, v in enumerate(lotes):
        if not isinstance(v, dict) or not v.get("artista"):
            continue
        rows.append({
            "chave":       f"tableau|{v.get('url_lote') or i}",
            "fonte":       "tableau",
            "artista":     _safe(v.get("artista")),
            "titulo":      _safe(v.get("titulo")),
            "tecnica":     _safe(v.get("tecnica")),
            "dimensoes":   _safe(v.get("medidas")),
            "lance_base":  _safe(v.get("valor_base")),
            "maior_lance": _safe(v.get("lance_atual")),
            "data_leilao": _safe(v.get("data_leilao")),
            "casa":        "Tableau Arte & Leilões",
            "url_detalhe": _safe(v.get("url_lote")),
            "foto_url":    _safe(v.get("img_grande") or v.get("img_thumb")),
            "em_leilao":   True,
            "data_coleta": _safe(v.get("coletado_em")),
            "lote_num":    _safe(v.get("lote_num")),
            "tiragem":     _safe(v.get("tiragem")),
            "assinado":    _safe(v.get("assinado")),
            "data_obra":   _safe(v.get("data_obra")),
            "tipo_lance":  _safe(v.get("tipo_lance")),
            "verbete_url": _safe(v.get("verbete_url")),
        })
    n = upsert_raw("lotes", rows)
    print(f"  [supabase] tableau: {n}/{len(rows)} registros sincronizados")
