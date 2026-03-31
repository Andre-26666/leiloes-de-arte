#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CCF Galeria de Arte — Scraper de Pinturas
Coleta lotes de pinturas em leilão em ccfgaleriadearte.com.br
Roda via GitHub Actions (garimpo.yml).
"""

import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Configuração ────────────────────────────────────────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(_DIR, "ccf_db.json")

BASE_URL  = "https://www.ccfgaleriadearte.com.br"
CASA      = "CCF Galeria de Arte"
DELAY     = 1.5   # segundos entre requisições
TIMEOUT   = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": BASE_URL + "/",
}

# Tipos de item a coletar (1=Quadros; 12=Aquarelas/Desenhos se existir)
TIPOS_ALVO = [1]

# Regex para extrair artista do início do h2 no formato "NOME. descrição"
_RE_ARTISTA = re.compile(
    r"^([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇa-záéíóúàâêôãõç\s'.\-]{2,60}?)\.\s",
)

# Regex para técnica
_RE_TECNICA = re.compile(
    r"((?:(?:tinta\s+a\s+)?[oó]leo|acr[ií]li[co]a?|aquarela|guache|gouache|"
    r"t[eé]mpera|mista|pastel|grafite|nanquim|sanguínea|carvão)"
    r"(?:\s+(?:sobre|s/)\s+\w+)?)",
    re.I,
)

# Regex para dimensões
_RE_DIMS = re.compile(r"(\d[\d\s,x×X\.]+\s*cm)", re.I)

# Regex para valor BRL
_RE_BRL = re.compile(r"R\$\s*([\d.,]+)")

# Regex para data
_RE_DATA = re.compile(
    r"dia\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
    re.I,
)
_MESES = {
    "janeiro":1,"fevereiro":2,"março":3,"março":3,"abril":4,"maio":5,
    "junho":6,"julho":7,"agosto":8,"setembro":9,"outubro":10,
    "novembro":11,"dezembro":12,
}


def _get(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"  ERRO get {url}: {e}")
        return None


def _parse_brl(txt: str) -> float:
    m = _RE_BRL.search(str(txt or ""))
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _parse_data(txt: str) -> str:
    """Converte 'dia 23 de Abril de 2026' → '23/4/2026'."""
    m = _RE_DATA.search(str(txt or "").lower())
    if not m:
        return ""
    d, mes_str, y = m.group(1), m.group(2).lower(), m.group(3)
    mes = _MESES.get(mes_str)
    if mes:
        return f"{d}/{mes}/{y}"
    return ""


def _extrair_artista(h2_text: str) -> str:
    """Extrai artista do início do h2: 'NOME. descrição...' → 'Nome'."""
    m = _RE_ARTISTA.match(h2_text.strip())
    if not m:
        return ""
    candidato = m.group(1).strip().rstrip(".")
    # Descarta se contém palavras de técnica (não é nome de artista)
    if _RE_TECNICA.search(candidato):
        return ""
    # Descarta se for muito longa
    if len(candidato.split()) > 6:
        return ""
    return candidato.title()   # converte BAPTISTA DA COSTA → Baptista da Costa


def _parse_detail(lot_id: str, auction_id: str) -> dict | None:
    """Raspa página de detalhe do lote. Retorna dict com campos ou None."""
    url = f"{BASE_URL}/peca.asp?Id={lot_id}"
    soup = _get(url)
    if not soup:
        return None

    # ── Texto principal (h2) ────────────────────────────────────────────────
    h2 = soup.find("h2")
    h2_text = h2.get_text(" ", strip=True) if h2 else ""

    artista = _extrair_artista(h2_text)

    # Técnica
    m_tec = _RE_TECNICA.search(h2_text)
    tecnica = m_tec.group(1).strip() if m_tec else ""

    # Dimensões — busca em todo o texto da página
    page_text = soup.get_text(" ")
    m_dim = _RE_DIMS.search(page_text)
    dimensoes = m_dim.group(1).strip() if m_dim else ""

    # Título = h2 sem o nome do artista na frente
    if artista and h2_text.startswith(artista.upper()):
        titulo = h2_text[len(artista):].lstrip(". ").strip()
    elif artista and ". " in h2_text:
        titulo = h2_text.split(". ", 1)[1].strip()
    else:
        titulo = h2_text

    # ── Preço base ──────────────────────────────────────────────────────────
    lance_base = 0.0
    for tag in soup.find_all(string=re.compile(r"valor\s+inicial", re.I)):
        parent = tag.parent
        # Tenta pegar o próximo elemento irmão ou texto após
        txt = parent.get_text(" ")
        lance_base = _parse_brl(txt)
        if lance_base:
            break

    # ── Data ────────────────────────────────────────────────────────────────
    data_leilao = _parse_data(page_text)

    # ── Foto ────────────────────────────────────────────────────────────────
    foto_url = (
        f"https://d1o6h00a1h5k7q.cloudfront.net"
        f"/imagens/img_g/{auction_id}/{lot_id}.jpg"
    )

    # ── Número do lote ──────────────────────────────────────────────────────
    num_lote = ""
    lote_link = soup.find("a", href=re.compile(r"#", re.I), string=re.compile(r"lote\s+\d+", re.I))
    if lote_link:
        num_lote = lote_link.get_text(strip=True)

    return {
        "artista":     artista,
        "titulo":      titulo[:300],
        "tecnica":     tecnica,
        "dimensoes":   dimensoes,
        "ano":         "",
        "lance_base":  lance_base,
        "maior_lance": 0.0,
        "num_lances":  0,
        "data_leilao": data_leilao,
        "casa":        CASA,
        "url_detalhe": url,
        "foto_url":    foto_url,
        "em_leilao":   True,
        "data_coleta": datetime.now().strftime("%Y-%m-%d"),
        "num_lote":    num_lote,
    }


def _get_lot_ids_from_catalog(auction_id: str, tipo: int) -> list[str]:
    """Retorna lista de IDs de lotes de uma página de catálogo (pagina até fim)."""
    lot_ids = []
    page = 1
    while True:
        url = f"{BASE_URL}/catalogo.asp?Num={auction_id}&Tipo={tipo}&p=on&pg={page}"
        soup = _get(url)
        if not soup:
            break

        # Links do tipo peca.asp?Id=NNNN
        links = soup.find_all("a", href=re.compile(r"peca\.asp\?Id=\d+", re.I))
        ids_pagina = list({
            re.search(r"Id=(\d+)", a["href"]).group(1)
            for a in links
            if re.search(r"Id=(\d+)", a["href"])
        })

        if not ids_pagina:
            break

        lot_ids.extend(ids_pagina)

        # Verifica se há próxima página
        prox = soup.find("a", string=re.compile(r"(próxima|seguinte|>)", re.I))
        if not prox:
            break
        page += 1
        time.sleep(DELAY)

    return lot_ids


def _get_active_auctions() -> list[dict]:
    """Busca leilões ativos na página principal. Retorna lista de {id, tipo}."""
    soup = _get(BASE_URL)
    if not soup:
        return []

    auctions = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"catalogo\.asp\?Num=\d+", re.I)):
        m = re.search(r"Num=(\d+)", a["href"])
        if m:
            aid = m.group(1)
            if aid not in seen:
                seen.add(aid)
                # Tipo padrão 1 (Quadros) — tentamos também sem tipo
                auctions.append({"id": aid})

    # Fallback: busca links de leilão de outras formas
    if not auctions:
        for a in soup.find_all("a", href=re.compile(r"leilao\.asp\?Num=\d+", re.I)):
            m = re.search(r"Num=(\d+)", a["href"])
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                auctions.append({"id": m.group(1)})

    return auctions


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 55)
    print(f"  CCF Galeria de Arte — Garimpo")
    print("=" * 55)

    db = load_db()
    novos = 0
    erros = 0

    # ── Descobre leilões ativos ─────────────────────────────────────────────
    print("Buscando leilões ativos...", end=" ", flush=True)
    auctions = _get_active_auctions()
    print(f"{len(auctions)} encontrados")

    if not auctions:
        print("Nenhum leilão ativo encontrado.")
        return

    for auction in auctions:
        aid = auction["id"]
        print(f"\n  Leilão #{aid}")

        for tipo in TIPOS_ALVO:
            print(f"    Tipo {tipo}: listando lotes...", end=" ", flush=True)
            lot_ids = _get_lot_ids_from_catalog(aid, tipo)
            print(f"{len(lot_ids)} lotes")

            for lot_id in lot_ids:
                chave = f"ccf|{lot_id}"

                # Pula se já temos dados recentes deste lote
                existing = db.get(chave)
                if existing and existing.get("em_leilao"):
                    continue

                time.sleep(DELAY)
                detail = _parse_detail(lot_id, aid)
                if not detail:
                    erros += 1
                    continue

                db[chave] = detail
                novos += 1

                artista_str = detail["artista"] or "(desconhecido)"
                print(f"      ✓ {lot_id} | {artista_str[:30]} | {detail['tecnica'][:20]} | R$ {detail['lance_base']:,.0f}")

    save_db(db)
    print(f"\n{'='*55}")
    print(f"  Novos/atualizados: {novos} | Erros: {erros}")
    print(f"  Total no DB: {len(db)}")

    # ── Sincroniza com Supabase ─────────────────────────────────────────────
    try:
        import supabase_sync
        if supabase_sync.enabled():
            print("\n  Sincronizando com Supabase...")
            supabase_sync.sync_ccf(db)
    except Exception as e:
        print(f"  [supabase] aviso: {e}")

    print("=" * 55)


if __name__ == "__main__":
    main()
