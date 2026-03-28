#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bolsa de Arte — Scraper de Cotações Históricas
Coleta estimativas e últimos lances de https://www.bolsadearte.com/artistas/cotacoes/
Execute com:  python catalogo_bolsadearte.py
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
DB_FILE = os.path.join(_DIR, "bolsadearte_db.json")

BASE_URL = "https://www.bolsadearte.com"
LIST_URL = BASE_URL + "/artistas/cotacoes/?page={page}"
MAX_PAGES = 1500
DELAY    = (2.0, 4.0)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.bolsadearte.com/",
}


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
    """'R$ 13.000,00' → 13000.0"""
    m = re.search(r"R\$\s*([\d.,]+)", txt)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass
    return 0.0


def get_text(el, selector: str) -> str:
    found = el.select_one(selector)
    if found:
        return found.get_text(strip=True)
    return ""


# ── Parse card ─────────────────────────────────────────────────────────────────
def parse_card(card) -> dict | None:
    info = card.select_one(".legendas-info-obras")
    if not info:
        return None

    # Link e URL detalhe
    link = info.select_one("a[href]")
    url  = (BASE_URL + link["href"]) if link and link.get("href") else ""

    # Foto
    img     = info.select_one("img")
    foto_url = img.get("src", "") if img else ""

    # Campos de texto por ícone FA
    paras = info.select("p")
    artista = titulo = tecnica = dimensoes = assinatura = ""
    estimativa_min = estimativa_max = lance = 0.0
    data_leilao = ""

    for p in paras:
        txt = p.get_text(strip=True)
        icon = p.select_one("i")
        cls  = icon.get("class", []) if icon else []

        if "fa-user" in cls:
            artista = re.sub(r"^Lote\s+\d+\s*", "", txt).strip()
        elif "fa-archive" in cls:
            pass  # número do lote — ignorar
        elif "fa-picture-o" in cls:
            titulo = txt
        elif "fa-pencil" in cls:
            tecnica = txt
        elif "fa-arrows" in cls:
            dimensoes = txt
        elif "fa-info-circle" in cls:
            assinatura = txt
        elif "fa-money" in cls:
            # Estimativa: R$ 10.000,00 - R$ 15.000,00
            nums = re.findall(r"R\$\s*([\d.,]+)", txt)
            if len(nums) >= 2:
                try:
                    estimativa_min = float(nums[0].replace(".", "").replace(",", "."))
                    estimativa_max = float(nums[1].replace(".", "").replace(",", "."))
                except ValueError:
                    pass
            elif len(nums) == 1:
                try:
                    estimativa_min = float(nums[0].replace(".", "").replace(",", "."))
                except ValueError:
                    pass
        elif "fa-line-chart" in cls:
            # Último lance: R$ 13.000,00 | US$ 2.360,00
            lance = parse_brl(txt)
        elif "fa-calendar" in cls:
            # Leilão: 29 de julho de 2025
            data_leilao = re.sub(r"^Leil[aã]o:\s*", "", txt, flags=re.I).strip()

    # Artista também pode ser o bold sem ícone
    if not artista:
        bold = info.select("p.bold")
        for b in bold:
            t = b.get_text(strip=True)
            if t and not t.startswith("Lote") and "Estimativa" not in t and "Último" not in t:
                artista = t
                break

    if not artista:
        return None

    key = url if url else f"BDA-{artista}-{titulo}".replace(" ", "_")

    return {
        "url_detalhe":    url,
        "foto_url":       foto_url,
        "artista":        artista,
        "titulo":         titulo,
        "tecnica":        tecnica,
        "dimensoes":      dimensoes,
        "assinatura":     assinatura,
        "estimativa_min": estimativa_min,
        "estimativa_max": estimativa_max,
        "lance_base":     estimativa_min,
        "maior_lance":    lance,
        "num_lances":     1 if lance > 0 else 0,
        "data_leilao":    data_leilao,
        "casa":           "bolsadearte.com",
        "ano":            "",
        "data_coleta":    datetime.now().strftime("%d/%m/%Y %H:%M"),
        "_key":           key,
    }


# ── Coleta ─────────────────────────────────────────────────────────────────────
def collect(session: requests.Session, db: dict):
    novos = 0
    meta  = db.setdefault("__meta__", {})
    full_done = meta.get("full_scan_done", False)

    if not full_done:
        start = meta.get("last_page", 0) + 1
        stop_thresh = 15
        print(f"  Modo: varredura completa | Início: pág {start}")
    else:
        start = 1
        stop_thresh = 3
        print(f"  Modo: incremental")

    pages_sem_novos = 0

    for page in range(start, MAX_PAGES + 1):
        url = LIST_URL.format(page=page)
        try:
            r = session.get(url, timeout=30)
        except Exception as e:
            print(f"  [ERRO] pág {page}: {e}")
            time.sleep(15)
            continue

        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}] pág {page}")
            break

        soup  = BeautifulSoup(r.text, "lxml")
        cards = soup.select("li.col-md-3, li[class*=col-sm]")

        if not cards:
            print(f"  Pág {page} sem cards — fim.")
            break

        novos_pag = 0
        for card in cards:
            item = parse_card(card)
            if not item:
                continue
            key = item.pop("_key")
            if key in db:
                continue
            db[key] = item
            novos += 1
            novos_pag += 1

        if not full_done:
            meta["last_page"] = page

        print(f"  Pág {page:>5} | +{novos_pag:>2} novos | Total novo: {novos}")

        if novos_pag > 0:
            save_db(db)

        if novos_pag == 0:
            pages_sem_novos += 1
            if pages_sem_novos >= stop_thresh:
                print(f"  {stop_thresh} páginas sem novos — parando.")
                break
        else:
            pages_sem_novos = 0

        time.sleep(random.uniform(*DELAY))

    if not full_done and page >= MAX_PAGES:
        meta["full_scan_done"] = True
        print("  [OK] Varredura completa marcada.")
        save_db(db)

    return novos


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Bolsa de Arte — Coletor de Cotações")
    print(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    db = load_db()
    obras = sum(1 for k in db if k != "__meta__")
    print(f"DB atual: {obras} cotações")

    session = requests.Session()
    session.headers.update(HEADERS)

    novos = collect(session, db)
    save_db(db)

    obras_final = sum(1 for k in db if k != "__meta__")
    print()
    print(f"Novos: {novos} | Total: {obras_final}")
    print(f"Salvo em: {DB_FILE}")
    print(f"Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")


if __name__ == "__main__":
    main()
