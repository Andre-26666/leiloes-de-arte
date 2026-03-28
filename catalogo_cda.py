#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catálogo das Artes — Scraper de Pinturas
Coleta dados de https://catalogodasartes.com.br/cotacao/pinturas/
Execute com:  python catalogo_cda.py
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
DB_FILE = os.path.join(_DIR, "cda_db.json")

BASE_URL     = "https://catalogodasartes.com.br"
LIST_URL     = BASE_URL + "/cotacao/pinturas/ordem/inclusao_mais_recente/pagina/{page}/"
MAX_PAGES    = 800        # limite por execução (aumentar conforme necessário)
DELAY_LIST   = (3.0, 6.0) # delay entre páginas de listagem
DELAY_DETAIL = (2.0, 4.0) # delay entre páginas de detalhe
MAX_DETAIL_PER_RUN = 0    # 0 = só listagem (rápido); aumentar para buscar detalhes
REQUEST_TIMEOUT = 35      # timeout por requisição

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── DB helpers ─────────────────────────────────────────────────────────────────
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ── Extração de lance da descrição ─────────────────────────────────────────────
def extract_lance_from_desc(desc: str) -> float:
    """Extrai 'lance inicial de R$X.XXX,XX' da descrição."""
    m = re.search(
        r"lance\s+inicial\s+de\s+R\$\s*([\d.,]+)",
        desc, re.I
    )
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass
    return 0.0


def extract_assinatura_from_desc(desc: str) -> str:
    """Extrai info de assinatura da descrição."""
    desc_l = desc.lower()
    if re.search(r"n[/.]?\s*ass|não\s+assinado|sem\s+assinatura", desc_l):
        return "Não assinado"
    if re.search(r"monogram", desc_l):
        return "Monogramado"
    if re.search(r"rubric", desc_l):
        return "Rubricado"
    if re.search(r"\bassin\b|a\.c\.i\.d|c\.i\.d|assinado|assinatura", desc_l):
        return "Assinado"
    return ""


# ── Scrape detalhe da obra ──────────────────────────────────────────────────────
def get_with_retry(session: requests.Session, url: str, retries: int = 3) -> requests.Response | None:
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    [429] Rate limit — aguardando {wait}s...")
                time.sleep(wait)
        except Exception as e:
            wait = 10 * (attempt + 1)
            print(f"    [TIMEOUT] tentativa {attempt+1}/{retries} — aguardando {wait}s...")
            time.sleep(wait)
    return None


def scrape_detail(session: requests.Session, url: str) -> dict:
    r = get_with_retry(session, url)
    if r is None:
        return {}

    soup = BeautifulSoup(r.text, "lxml")
    data = {}

    # Itemprop fields
    ip = {}
    for el in soup.select("[itemprop]"):
        prop = el.get("itemprop", "")
        val  = el.get("content") or el.get_text(strip=True)
        if prop and val and prop not in ip:
            ip[prop] = val

    data["tecnica"]  = ip.get("material", "")
    data["ano"]      = ip.get("dateCreated", "")

    # Dimensões do detalhe (width x height)
    w = ip.get("width", "")
    h = ip.get("height", "")
    if w and h:
        try:
            wi = int(float(w))
            hi = int(float(h))
            data["dimensoes"] = f"{wi}x{hi}cm"
        except Exception:
            pass

    # Descrição completa (texto do bloco de descrição)
    desc_el = soup.find(string=re.compile(r"Descrição", re.I))
    if desc_el:
        parent = desc_el.parent
        # Pega o próximo sibling com texto
        nxt = parent.find_next_sibling()
        if nxt:
            data["descricao"] = nxt.get_text(strip=True)
    # Fallback: procura diretamente
    if not data.get("descricao"):
        for el in soup.select(".descricao, [class*=descri]"):
            txt = el.get_text(strip=True)
            if txt:
                data["descricao"] = txt
                break

    desc = data.get("descricao", "")

    # Status (vendida / em leilão / não vendida)
    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
    if re.search(r"vendida", body_text, re.I) and not re.search(r"não\s+vendida", body_text, re.I):
        data["status"] = "Vendida"
    elif re.search(r"não\s+vendida|nao\s+vendida", body_text, re.I):
        data["status"] = "Não vendida"
    elif re.search(r"em\s+leilão|em\s+leilao", body_text, re.I):
        data["status"] = "Em leilão"
    else:
        data["status"] = ""

    # Data da pesquisa
    m_data = re.search(r"Data\s+da\s+Pesquisa\s+(\d{2}/\d{2}/\d{4})", body_text)
    if m_data:
        data["data_pesquisa"] = m_data.group(1)

    # Lance inicial extraído da descrição
    data["lance_base"] = extract_lance_from_desc(desc)

    # Assinatura
    data["assinatura"] = extract_assinatura_from_desc(desc)

    # Fonte: URL de leilão mencionada na descrição
    m_fonte = re.search(r"https?://[^\s\)]+", desc)
    if m_fonte:
        data["fonte_url"] = m_fonte.group(0)

    return data


# ── Parse card de listagem ──────────────────────────────────────────────────────
def parse_card(card) -> dict:
    data = {}

    link = card.select_one("a[href*='/obra/']")
    if not link:
        return {}
    data["url_detalhe"] = link["href"].strip()

    img = card.select_one("img[itemprop=image]")
    if img:
        data["foto_url"] = img.get("src", "").strip()

    artista_el = card.select_one("[itemprop=name]")
    if artista_el:
        data["artista"] = artista_el.get("content") or artista_el.get_text(strip=True)

    titulo_el = card.select_one(".titulo")
    if titulo_el:
        data["titulo"] = titulo_el.get("content") or titulo_el.get_text(strip=True)

    tecnica_el = card.select_one(".tecnica")
    if tecnica_el:
        data["tecnica"] = tecnica_el.get("content") or tecnica_el.get_text(strip=True)

    # Dimensões
    w_el = card.select_one("[itemprop=width] [itemprop=value]")
    h_el = card.select_one("[itemprop=height] [itemprop=value]")
    if w_el and h_el:
        try:
            wi = int(float(w_el.get("content") or w_el.get_text(strip=True)))
            hi = int(float(h_el.get("content") or h_el.get_text(strip=True)))
            data["dimensoes"] = f"{wi}x{hi}cm"
        except Exception:
            pass

    data["casa"]  = "catalogodasartes.com.br"
    data["maior_lance"] = 0.0
    data["num_lances"]  = 0
    data["lance_base"]  = 0.0
    data["assinatura"]  = ""
    data["status"]      = ""
    data["ano"]         = ""
    data["descricao"]   = ""
    data["fonte_url"]   = ""
    data["data_pesquisa"] = ""
    data["data_coleta"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    return data


# ── Coleta páginas de listagem ──────────────────────────────────────────────────
def collect(session: requests.Session, db: dict, db_inicial: int = 0):
    novos       = 0
    detail_cnt  = 0
    pages_sem_novos = 0

    meta = db.setdefault("__meta__", {})
    varredura_completa = meta.get("full_scan_done", False)

    # Coleta completa: começa da última página coletada + 1 (ou página 1 para incremental)
    if not varredura_completa:
        start_page = meta.get("last_page", 0) + 1
        stop_threshold = 20
        print(f"  Modo: varredura completa | Início: pág {start_page}")
    else:
        start_page = 1
        stop_threshold = 3
        print(f"  Modo: incremental")

    for page in range(start_page, MAX_PAGES + 1):
        url = LIST_URL.format(page=page)
        r = get_with_retry(session, url)
        if r is None:
            print(f"  [FALHOU] pág {page} após retries — pulando")
            continue

        soup  = BeautifulSoup(r.text, "lxml")
        cards = soup.select(".card.produto")

        if not cards:
            print(f"  Página {page} sem cards — fim.")
            break

        novos_nesta_pagina = 0
        for card in cards:
            item = parse_card(card)
            if not item or not item.get("url_detalhe"):
                continue

            key = item["url_detalhe"]

            if key in db:
                continue  # já coletado

            # Busca detalhe se cota de detalhes não atingida
            if detail_cnt < MAX_DETAIL_PER_RUN:
                time.sleep(random.uniform(*DELAY_DETAIL))
                extra = scrape_detail(session, key)
                item.update({k: v for k, v in extra.items() if v})
                detail_cnt += 1

            db[key] = item
            novos += 1
            novos_nesta_pagina += 1

        print(
            f"  Pág {page:>5} | +{novos_nesta_pagina:>2} novos "
            f"| Total novo: {novos} | Detalhes: {detail_cnt}"
        )

        # Salva a cada página para não perder progresso
        if novos_nesta_pagina > 0:
            save_db(db)

        # Salva última página no meta para retomar depois
        if not varredura_completa:
            meta["last_page"] = page

        if novos_nesta_pagina == 0:
            pages_sem_novos += 1
            if pages_sem_novos >= stop_threshold:
                print(f"  {stop_threshold} páginas consecutivas sem novos — parando.")
                break
        else:
            pages_sem_novos = 0

        time.sleep(random.uniform(*DELAY_LIST))

    # Marca varredura completa se chegou no final (MAX_PAGES ou site sem mais cards)
    if not varredura_completa and (page >= MAX_PAGES or not cards):
        meta["full_scan_done"] = True
        meta["last_page"] = MAX_PAGES
        print("  [OK] Varredura completa marcada — próximas execuções serão incrementais.")
        save_db(db)

    return novos


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Catálogo das Artes — Coletor de Pinturas")
    print(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    db = load_db()
    print(f"DB atual: {len(db)} obras")

    session = requests.Session()
    session.headers.update(HEADERS)

    novos = collect(session, db, db_inicial=len(db))
    save_db(db)

    print()
    print(f"Novos: {novos} | Total: {len(db)}")
    print(f"Salvo em: {DB_FILE}")
    print(f"Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")


if __name__ == "__main__":
    main()
