#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
historico_casas.py
──────────────────
Raspa resultados históricos de casas de leilão que publicam
"Valor de venda: R$ X" diretamente no HTML do catálogo ASP.

Fontes:
  - levyleiloeiro.com.br    (123+ páginas de catálogos)
  - conradoleiloeiro.com.br (52+ páginas de catálogos)

Gera: historico_casas_db.json
Formato compatível com load_media_hist() da plataforma.

Uso:
  python historico_casas.py                  # todas as casas, incremental
  python historico_casas.py --casa levy      # só Levy
  python historico_casas.py --casa conrad    # só Conrad
  python historico_casas.py --max-cat 10     # limita catálogos por casa
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────
_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_FILE   = os.path.join(_DIR, "historico_casas_db.json")

DELAY     = 1.2   # segundos entre requests
MAX_PAGES = 99    # páginas por catálogo

CASAS = {
    "levy": {
        "nome":  "Levy Leiloeiro",
        "base":  "https://www.levyleiloeiro.com.br",
        "lista": "/listacatalogo.asp",
        "probe_range": (4000, 4107),  # sonda catálogos retroativos
    },
    "conrad": {
        "nome":  "Conrad Leiloeiro",
        "base":  "https://www.conradoleiloeiro.com.br",
        "lista": "/listacatalogo.asp",
    },
    "miguelsalles": {
        "nome":  "Miguel Salles",
        "base":  "https://www.miguelsalles.com.br",
        "lista": "/listacatalogo.asp",
    },
    "dagsaboya": {
        "nome":  "Dag Saboya",
        "base":  "https://br.dagsaboya.com.br",
        "lista": "/listacatalogo.asp",
    },
    "andreadiniz": {
        "nome":  "Andrea Diniz",
        "base":  "https://www.andreadiniz.com.br",
        "lista": "/listacatalogo.asp",
    },
    "marciopinho": {
        "nome":  "Marcio Pinho",
        "base":  "https://www.marciopinho.lel.br",
        "lista": "/listacatalogo.asp",
    },
    "leilaodeartebrasileira": {
        "nome":  "Leilão de Arte Brasileira",
        "base":  "https://www.leilaodeartebrasileira.com.br",
        "lista": "/listacatalogo.asp",
    },
    "rmgouvea": {
        "nome":  "RM Gouvea Leilões",
        "base":  "https://www.rmgouvealeiloes.com.br",
        "lista": "/listacatalogo.asp",
    },
    "jonas": {
        "nome":  "Jonas Leilões",
        "base":  "https://www.jonas.lel.br",
        "lista": "/listacatalogo.asp",
    },
}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
}

# ── Termos que indicam obra de arte com artista ────────────────────────────────
_RE_ARTISTA_SEP = re.compile(r'^([A-ZÁÉÍÓÚÀÂÊÔÃÕÜÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÜÇa-záéíóúàâêôãõüç\s\.\-\']{3,50})\s*[-–|]\s*.+', re.UNICODE)
_RE_PRECO       = re.compile(r'R\$\s*([\d.,]+)', re.I)

# Termos na descrição que confirmam obra de arte
_ARTE_TERMS = re.compile(
    r'\b(pintura|tela|telas|aquarela|óleo|oleo|acrílica|acrilica|guache|pastel|'
    r'gravura|litografia|serigrafia|xilogravura|nanquim|têmpera|tempera|'
    r'escultura|bronze|mármor|mármore|desenho|crayon|carvão|monotipia|'
    r'fotografia|impressão|giclée|giclee|obra|quadro|tapeçaria|tapecaria|'
    r'assinado|assinada|monogramado)\b',
    re.I | re.UNICODE,
)


# ── HTTP ──────────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, **kw) -> requests.Response | None:
    try:
        r = session.get(url, timeout=20, **kw)
        if r.status_code == 200:
            return r
    except Exception as e:
        print(f"    [erro] {url}: {e}")
    return None


# ── Parse ─────────────────────────────────────────────────────────────────────
def _limpa_preco(s: str) -> float:
    """'1.200,50' → 1200.50  |  '59.00' → 59.0  |  '3.800,00' → 3800.0"""
    s = s.strip()
    if "," in s:
        # Formato brasileiro: 1.200,50 — ponto é milhar, vírgula é decimal
        s = s.replace(".", "").replace(",", ".")
    # Sem vírgula: formato americano (59.00) ou inteiro — já está correto
    try:
        return float(s)
    except Exception:
        return 0.0


def _extrai_artista(h3_text: str) -> str:
    """
    '- 3331 - ALDEMIR MARTINS - GATO | ÓLEO SOBRE TELA...' → 'ALDEMIR MARTINS'
    Retorna '' se não reconhece padrão de artista.
    """
    t = h3_text.strip()
    # Remove padrões de número de lote: "- 123 -" ou "123 -" no início
    t = re.sub(r'^[-–\s]*\d+\s*[-–]\s*', '', t).strip()
    t = re.sub(r'^[-–\s]*\d+\s*[-–]\s*', '', t).strip()  # dupla remoção para "- 123 - 456 -"
    m = _RE_ARTISTA_SEP.match(t)
    if not m:
        return ""
    candidato = m.group(1).strip()
    if len(candidato) < 4:
        return ""
    if candidato[0].isdigit():
        return ""
    # Rejeita palavras que são claramente objetos, locais ou não-artistas
    _rejeitar = re.compile(
        r'^(conjunto|vintage|antiga|antigo|par |lote |porcelana|cristal|prata|'
        r'bronze(?! \w)|móvel|móveis|livro|livros|medida|miniatura|coleção|'
        r'japan|china|france|germany|usa|made in|signed|'
        r'egypt|england|brasil|portugal|espanha|italia|austria|'
        r'minas gerais|rio de|são paulo|rio grande|santa catarina|'
        r'sino |talha |bandeja|travessa|xícara|xcara|prato |pratos |'
        r'relógio|relogio|binóculo|binoculo|bengala|vitrine|luminária|'
        r'aeromodelismo|decoraç|escultura com|imagem |nariz|ex.voto|'
        r'caixinha|caixa |moinho|moedor|caldeirão|jarra|vaso |vasos |'
        r'mega |fisher|vintage)',
        re.I | re.UNICODE,
    )
    if _rejeitar.match(candidato):
        return ""
    # Rejeita candidatos que são apenas UMA palavra em maiúsculas (ex: "EGYPT", "ENGLAND")
    palavras = candidato.split()
    if len(palavras) == 1 and candidato.isupper() and len(candidato) <= 8:
        return ""
    # Corta o artista no primeiro " - " (evita capturar título junto: "SONIA EEBLING - MULHER")
    if " - " in candidato:
        candidato = candidato.split(" - ")[0].strip()
        if len(candidato) < 4:
            return ""
    return candidato


def _parse_lote(div) -> dict | None:
    """
    Extrai artista e valor de venda de um div de lote.
    Suporta dois padrões:
      - Levy/Conrad: texto "Valor de venda: R$ X" no HTML
      - V8.9 (leiloesbr): div.lotevendido + p.price-bid
    """
    h3 = div.find("h3")
    if not h3:
        return None
    texto = h3.get_text(" ", strip=True)

    artista = _extrai_artista(texto)
    if not artista:
        return None

    # Confirma que é obra de arte
    if not _ARTE_TERMS.search(texto):
        return None

    div_text = div.get_text(" ", strip=True)
    preco = 0.0

    # Padrão 1: "Valor de venda: R$ X" (Levy, Conrad e similares)
    idx = div_text.lower().find("valor de venda")
    if idx >= 0:
        m_preco = _RE_PRECO.search(div_text[idx:])
        if m_preco:
            preco = _limpa_preco(m_preco.group(1))

    # Padrão 2: V8.9 — div.lotevendido presente + p.price-bid com preço
    if preco < 50:
        vendido = div.find(class_=re.compile(r"lote.?vendido|sold", re.I))
        if vendido:
            pbid = div.find("p", class_=re.compile(r"price.?bid|lance", re.I))
            if pbid:
                m_preco = _RE_PRECO.search(pbid.get_text())
                if m_preco:
                    preco = _limpa_preco(m_preco.group(1))

    if preco < 50:
        return None

    # Extrai título: o que vem depois do artista, antes do " | "
    partes = re.split(r'\s*[-–]\s*', texto, maxsplit=3)
    titulo = ""
    for p in partes[1:]:
        cand = p.split("|")[0].strip()
        if cand and cand != artista and not cand.isdigit():
            titulo = cand[:120]
            break

    return {
        "artista":     artista,
        "titulo":      titulo,
        "maior_lance": preco,
        "em_leilao":   False,
        "fonte":       "",
    }


def _find_lote_containers(soup) -> list:
    """
    Tenta várias estratégias para localizar os divs de lote na página.
    Retorna lista de elementos BeautifulSoup.
    """
    # Estratégia 1: product-content — padrão V8.9 principal (Levy, Miguel Salles, etc.)
    divs = soup.find_all("div", class_=re.compile(r"\bproduct-content\b", re.I))
    if divs:
        return divs

    # Estratégia 2: outras classes explícitas
    for cls in ("lot-container", "lote-item"):
        divs = soup.find_all("div", class_=cls)
        if divs:
            return divs

    # Estratégia 3: subir pelo "Valor de venda" até achar ancestral com H3
    containers = []
    vistos = set()
    for tag in soup.find_all(string=re.compile(r"valor de venda", re.I)):
        node = tag.parent
        for _ in range(8):
            if node is None or node.name == "body":
                break
            if node.name == "div" and node.find("h3"):
                if id(node) not in vistos:
                    vistos.add(id(node))
                    containers.append(node)
                break
            node = node.parent
    if containers:
        return containers

    # Estratégia 4: div.lotevendido → sobe até encontrar H3 (V8.9 finalizados)
    containers = []
    vistos = set()
    for vendido in soup.find_all(class_=re.compile(r"lote.?vendido", re.I)):
        node = vendido.parent
        for _ in range(6):
            if node is None or node.name == "body":
                break
            if node.name == "div" and node.find("h3"):
                if id(node) not in vistos:
                    vistos.add(id(node))
                    containers.append(node)
                break
            node = node.parent
    if containers:
        return containers

    # Estratégia 5: fallback — ancestral div de cada H3
    vistos = set()
    containers = []
    for h3 in soup.find_all("h3"):
        node = h3.find_parent("div")
        if node and id(node) not in vistos:
            vistos.add(id(node))
            containers.append(node)
    return containers


def _lot_id(div) -> str:
    """Extrai ID único do lote do link peca.asp?ID=XXXX (para dedup)."""
    a = div.find("a", href=re.compile(r"peca\.asp\?ID=\d+", re.I))
    if a:
        m = re.search(r"ID=(\d+)", a.get("href", ""))
        if m:
            return m.group(1)
    # Fallback: texto do H3
    h3 = div.find("h3")
    return h3.get_text(" ", strip=True)[:60] if h3 else ""


def scrape_catalogo(base_url: str, num: int, nome_casa: str) -> list[dict]:
    """Raspa todos os lotes de arte vendidos em um catálogo."""
    lotes = []
    vistos_ids: set = set()
    for pag in range(1, MAX_PAGES + 1):
        url = f"{base_url}/catalogo.asp?Num={num}&pag={pag}"
        r = get(url)
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")

        divs = _find_lote_containers(soup)
        for div in divs:
            lid = _lot_id(div)
            if lid and lid in vistos_ids:
                continue  # dedup mobile/desktop
            lote = _parse_lote(div)
            if lote:
                if lid:
                    vistos_ids.add(lid)
                lote["fonte"] = nome_casa
                lotes.append(lote)

        # Verifica se há próxima página
        prox = (
            soup.find("a", string=re.compile(r"próxima|next|>|»", re.I)) or
            soup.find("a", href=re.compile(rf"[?&]pag={pag+1}"))
        )
        if not prox:
            break

        time.sleep(DELAY * 0.5)

    return lotes


def scrape_listacatalogo(base_url: str, lista_path: str, probe_range: tuple = None) -> list[tuple[int, str]]:
    """
    Retorna lista de (num_catalogo, descricao) dos catálogos DESTA casa.
    Se probe_range=(ini, fim) é fornecido, também sonda catálogos por número sequencial.
    """
    catalogos = []
    nums_vistos: set = set()

    # ── 1. Listagem normal via listacatalogo.asp ──────────────────────────────
    pag = 1
    while True:
        url = f"{base_url}{lista_path}?pag={pag}"
        r = get(url)
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")
        links = soup.find_all("a", href=re.compile(r"catalogo\.asp\?Num=\d+", re.I))
        novos = 0
        for a in links:
            href = a.get("href", "")
            if href.startswith("http") and base_url not in href:
                continue
            m = re.search(r"Num=(\d+)", href)
            if not m:
                continue
            num = int(m.group(1))
            if num not in nums_vistos:
                nums_vistos.add(num)
                catalogos.append((num, a.get_text(" ", strip=True)[:80]))
                novos += 1
        if novos == 0:
            break
        prox = soup.find("a", href=re.compile(rf"pag={pag+1}"))
        if not prox:
            break
        pag += 1
        time.sleep(DELAY * 0.3)

    # ── 2. Sondagem por range (catálogos retroativos não listados) ────────────
    if probe_range:
        ini, fim = probe_range
        print(f"    [probe] sondando range {ini}-{fim-1}...", end=" ", flush=True)
        encontrados = 0
        for num in range(ini, fim):
            if num in nums_vistos:
                continue
            url = f"{base_url}/catalogo.asp?Num={num}&pag=1"
            r = get(url)
            if not r:
                time.sleep(DELAY * 0.2)
                continue
            soup = BeautifulSoup(r.text, "lxml")
            pcs = soup.find_all("div", class_=re.compile(r"\bproduct-content\b", re.I))
            if pcs:
                nums_vistos.add(num)
                catalogos.append((num, ""))
                encontrados += 1
            time.sleep(DELAY * 0.2)
        print(f"{encontrados} catálogos adicionais")

    return catalogos


# ── DB ────────────────────────────────────────────────────────────────────────
def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"__meta": {"criado": datetime.now().isoformat()}, "catalogos_ok": [], "lotes": []}


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casa", choices=list(CASAS.keys()), help="Processar só esta casa")
    ap.add_argument("--max-cat", type=int, default=0, help="Máximo de catálogos por casa (0=todos)")
    args = ap.parse_args()

    db = load_db()
    catalogos_ok: set = set(db.get("catalogos_ok", []))
    lotes_db: list = db.get("lotes", [])

    casas_alvo = {args.casa: CASAS[args.casa]} if args.casa else CASAS

    total_novos = 0
    for chave, cfg in casas_alvo.items():
        nome  = cfg["nome"]
        base  = cfg["base"]
        lista = cfg["lista"]
        print(f"\n{'='*60}")
        print(f"  {nome}")
        print(f"{'='*60}")

        print("  Coletando lista de catálogos...", end=" ", flush=True)
        probe = cfg.get("probe_range")
        catalogos = scrape_listacatalogo(base, lista, probe_range=probe)
        proprios = catalogos
        print(f"{len(proprios)} catálogos encontrados")

        # Limita se pedido
        max_c = args.max_cat or cfg.get("max_cat", 999)
        proprios = proprios[:max_c]

        novos_casa = 0
        for i, (num, desc) in enumerate(proprios):
            chave_cat = f"{chave}_{num}"
            if chave_cat in catalogos_ok:
                continue  # já processado

            print(f"  [{i+1:03d}/{len(proprios)}] cat#{num} — {desc[:50]}", end=" ", flush=True)
            lotes = scrape_catalogo(base, num, nome)
            print(f"→ {len(lotes)} lotes de arte")

            lotes_db.extend(lotes)
            catalogos_ok.add(chave_cat)
            novos_casa += len(lotes)

            # Salva a cada 10 catálogos
            if (i + 1) % 10 == 0:
                db["catalogos_ok"] = list(catalogos_ok)
                db["lotes"] = lotes_db
                save_db(db)

            time.sleep(DELAY)

        total_novos += novos_casa
        print(f"\n  {nome}: {novos_casa} lotes novos coletados")

    db["catalogos_ok"] = list(catalogos_ok)
    db["lotes"] = lotes_db
    db["__meta"]["atualizado"] = datetime.now().isoformat()
    save_db(db)

    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_novos} lotes novos | {len(lotes_db)} no DB")
    print(f"  Arquivo: {DB_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
