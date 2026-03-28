#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arremate Arte — Scraper para TNT Arte e Alexei Arremate
Coleta lotes de https://www.tntarte.com.br e https://alexei.arrematearte.com.br
Execute com:  python catalogo_arrematearte.py
"""

import json
import os
import re
import time
import random
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Configuração ───────────────────────────────────────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(_DIR, "arrematearte_db.json")

SITES = {
    "tntarte": {
        "base":    "https://www.tntarte.com.br",
        "casa":    "tntarte.com.br",
        "min_id":  50,   # IDs baixos não existem
        "max_id":  300,
    },
    "alexei": {
        "base":    "https://alexei.arrematearte.com.br",
        "casa":    "alexei.arrematearte.com.br",
        "min_id":  1,
        "max_id":  100,
    },
}

DELAY  = (2.0, 4.0)
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Só pinturas — filtra pela descrição/técnica
PINTURA_KW = [
    "óleo", "oleo", "acrílica", "acrilica", "acrílico", "acrilico",
    "aquarela", "guache", "gouache", "pastel", "têmpera", "tempera",
    "técnica mista", "tecnica mista", "tinta", "nanquim", "encáustica",
    "tela", "madeira", "papel", "eucatex", "mdf", "compensado", "cartão",
]

GRAVURA_KW = [
    "serigrafia", "gravura", "xilogravura", "litografia",
    "água-forte", "agua-forte", "monotipia", "offset", "impressão",
    "serigraph", "lithograph", "etching",
]


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def parse_brl(txt: str) -> float:
    m = re.search(r"R\$\s*([\d.,]+)", txt or "")
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            pass
    return 0.0


def is_pintura(txt: str) -> bool:
    t = txt.lower()
    if any(k in t for k in GRAVURA_KW):
        return False
    return any(k in t for k in PINTURA_KW)


def detect_assinatura(txt: str) -> str:
    t = txt.lower()
    if re.search(r"n[/.]?\s*ass|não\s+assinado|sem\s+assinatura", t):
        return "Não assinado"
    if re.search(r"monogram", t):
        return "Monogramado"
    if re.search(r"rubric", t):
        return "Rubricado"
    if re.search(r"ass[:.]?\s*c\.i|ass[:.]?\s*c\.s|assinado|assinatura|\bass\b", t):
        return "Assinado"
    return ""


def parse_dimensoes(txt: str) -> str:
    m = re.search(r"(\d+(?:[.,]\d+)?\s*[xX×]\s*\d+(?:[.,]\d+)?\s*(?:cm|mm)?)", txt)
    return m.group(1).strip() if m else ""


def parse_ano(txt: str) -> str:
    m = re.search(r"\b(1[89]\d{2}|20[012]\d)\b", txt)
    return m.group(1) if m else ""


def parse_tecnica(desc: str) -> str:
    """Extrai técnica da descrição — padrão: 'Autor – Técnica, med: ...'"""
    # Após o dash: "Óleo Sobre Tela, med:..."
    m = re.search(
        r"[–\-]\s*((?:óleo|oleo|acrílica|acrilica|acrílico|acrilico|aquarela|"
        r"guache|gouache|pastel|têmpera|tempera|técnica mista|tecnica mista|"
        r"tinta|nanquim)[^,.]*)",
        desc, re.I
    )
    if m:
        return m.group(1).strip()
    # Fallback: procura keywords direto
    for kw in PINTURA_KW:
        if kw in desc.lower():
            idx = desc.lower().index(kw)
            return desc[idx:idx+60].split(",")[0].strip()
    return ""


# ── Parser de card ─────────────────────────────────────────────────────────────
def parse_card(card, base_url: str, casa: str) -> dict | None:
    # Status (ativo/finalizado)
    bid_tag = card.select_one(".bid-tag")
    status_txt = bid_tag.get_text(strip=True).lower() if bid_tag else ""
    em_leilao = "lance" in status_txt or "lote" in status_txt or "live" in status_txt

    # Href do lote
    lot_link = card.select_one("span.lot-link")
    href = lot_link.get("href", "") if lot_link else ""
    url_detalhe = (base_url + href) if href else ""

    # Foto
    img = card.select_one("img[src]")
    foto_url = img["src"].split("?")[0] if img else ""

    # Artista
    artista_el = card.select_one("span.lot-author__text-name")
    artista = artista_el.get_text(strip=True) if artista_el else ""

    # Título (existe no TNT, não no Alexei)
    titulo_el = card.select_one("h3.text__title")
    titulo = titulo_el.get_text(strip=True) if titulo_el else ""

    # Descrição completa
    desc_el = card.select_one("div.text__description")
    descricao = desc_el.get_text(strip=True) if desc_el else ""

    # Extrai técnica da descrição quando não há título separado
    tecnica = parse_tecnica(descricao)

    # Preço BRL
    preco_el = card.select_one("span.js-current-currency[data-code='BRL']")
    preco = parse_brl(preco_el.get_text(strip=True)) if preco_el else 0.0

    # Preço via data-amount-cents (fallback, mais confiável)
    cents_el = card.select_one("span.js-current-currency[data-amount-cents]")
    if cents_el and preco == 0.0:
        try:
            preco = int(cents_el["data-amount-cents"]) / 100
        except Exception:
            pass

    # Número do lote
    lot_num_el = card.select_one("span.content__lot")
    lot_num = lot_num_el.get_text(strip=True) if lot_num_el else ""

    # data-lot-id como chave única
    btn = card.select_one("button.like-it[data-lot-id]")
    lot_id = btn["data-lot-id"] if btn else ""

    if not lot_id and not url_detalhe:
        return None
    if not artista and not descricao:
        return None

    key = f"{casa}_{lot_id}" if lot_id else url_detalhe

    return {
        "_key":        key,
        "url_detalhe": url_detalhe,
        "foto_url":    foto_url,
        "artista":     artista,
        "titulo":      titulo or descricao[:80],
        "tecnica":     tecnica,
        "dimensoes":   parse_dimensoes(descricao),
        "assinatura":  detect_assinatura(descricao),
        "ano":         parse_ano(descricao),
        "descricao":   descricao,
        "lot_num":     lot_num,
        "lance_base":  preco,
        "maior_lance": preco,
        "num_lances":  1 if preco > 0 else 0,
        "em_leilao":   em_leilao,
        "status":      "Em leilão" if em_leilao else (
                       "Arrematado" if "arrematado" in status_txt else
                       "Não vendido" if "não vendido" in status_txt else ""),
        "casa":        casa,
        "data_coleta": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


# ── Coleta um leilão ────────────────────────────────────────────────────────────
def scrape_auction(session: requests.Session, base: str, casa: str,
                   auction_id: int) -> list[dict]:
    url = f"{base}/leiloes/{auction_id}/catalogo"
    try:
        r = session.get(url, timeout=TIMEOUT)
    except Exception as e:
        return []

    if r.status_code == 404:
        return []
    if r.status_code != 200:
        print(f"    [HTTP {r.status_code}] {url}")
        return []

    soup  = BeautifulSoup(r.text, "lxml")
    cards = soup.select("div.spotlight__item")
    if not cards:
        return []

    items = []
    for card in cards:
        item = parse_card(card, base, casa)
        if not item:
            continue
        desc = (item.get("tecnica") or "") + " " + (item.get("descricao") or "")
        if not is_pintura(desc):
            continue
        items.append(item)

    return items


# ── Coleta um site completo ────────────────────────────────────────────────────
def collect_site(session: requests.Session, db: dict, site_key: str):
    cfg      = SITES[site_key]
    base     = cfg["base"]
    casa     = cfg["casa"]
    max_id   = cfg["max_id"]
    meta_key = f"__meta_{site_key}__"
    meta     = db.setdefault(meta_key, {})

    min_id   = cfg.get("min_id", 1)
    last_ok  = meta.get("last_ok_id", 0)
    novos    = 0
    falhas_seguidas = 0

    start = max(min_id, last_ok - 2) if last_ok > 0 else min_id
    print(f"\n  [{casa}] Varrendo IDs {start}..{max_id} (último OK: {last_ok})")

    for aid in range(start, max_id + 1):
        items = scrape_auction(session, base, casa, aid)

        if not items:
            falhas_seguidas += 1
            if falhas_seguidas >= 15:
                print(f"    15 IDs consecutivos vazios — parando {casa}")
                break
            continue

        falhas_seguidas = 0

        novos_leilao = 0
        for item in items:
            key = item.pop("_key")
            if key in db:
                # Atualiza status em_leilao e lance se já existe
                db[key]["em_leilao"] = item["em_leilao"]
                if item["maior_lance"] > 0:
                    db[key]["maior_lance"] = item["maior_lance"]
                continue
            db[key] = item
            novos += 1
            novos_leilao += 1

        if items:
            if aid > last_ok:
                meta["last_ok_id"] = aid
                last_ok = aid
            if novos_leilao > 0:
                print(f"    Leilão {aid:>3}: +{novos_leilao} pinturas")
                save_db(db)

        time.sleep(random.uniform(*DELAY))

    return novos


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Arremate Arte — TNT Arte + Alexei Arremate")
    print(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    db = load_db()
    obras = sum(1 for k in db if not k.startswith("__meta"))
    print(f"DB atual: {obras} obras")

    session = requests.Session()
    session.headers.update(HEADERS)

    total_novos = 0
    for site_key in SITES:
        novos = collect_site(session, db, site_key)
        total_novos += novos
        print(f"  [{site_key}] +{novos} novas pinturas")

    save_db(db)

    obras_final = sum(1 for k in db if not k.startswith("__meta"))
    print()
    print(f"Novos: {total_novos} | Total: {obras_final}")
    print(f"Salvo em: {DB_FILE}")
    print(f"Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")


if __name__ == "__main__":
    main()
