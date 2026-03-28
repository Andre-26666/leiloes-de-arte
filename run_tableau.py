#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import re, json, time, os
from datetime import datetime
from collections import Counter

BASE_URL  = "https://www.tableau.com.br"
LOTE_URL  = BASE_URL + "/leilao/lote.php?lote={n}"
IMG_BASE  = BASE_URL + "/leilao/"
_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_FILE   = os.path.join(_DIR, "tableau_db.json")
XLSX_FILE = os.path.join(_DIR, "tableau_leilao_analise.xlsx")
DELAY     = 0.6
MAX_VAZIOS = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

def parse_lote(html_content, n):
    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    table = soup.find("table")
    if not table:
        return None
    tds = table.find_all("td")
    if len(tds) < 2:
        return None
    td_img  = tds[0]
    td_data = tds[1]

    img_tag = td_img.find("img")
    img_src = img_tag.get("src", "") if img_tag else ""
    img_url_thumb  = IMG_BASE + img_src if img_src else ""
    img_url_grande = IMG_BASE + img_src.replace(".jpg", "g.jpg") if img_src else ""

    full_text = td_data.get_text(separator="\n", strip=True)

    lote_num   = n
    tipo_lance = ""
    m_lote = re.search(r"Lote\s+N[o\xba\xb0]?\s*(\d+)\s*[-\u2013]\s*([^\n]+)", full_text, re.IGNORECASE)
    if m_lote:
        lote_num   = int(m_lote.group(1))
        tipo_lance = m_lote.group(2).strip()

    valor_base  = None
    lance_atual = None
    m_oferta = re.search(r"Temos oferta de:\s*R\$\s*([\d.,]+)", full_text, re.IGNORECASE)
    if m_oferta:
        v = m_oferta.group(1).replace(".", "").replace(",", ".")
        try:
            lance_atual = float(v)
            valor_base  = lance_atual
        except Exception:
            pass

    data_leilao = ""
    m_dia = re.search(r"Dia do Leil[a\xe3]o:\s*([^\n]+)", full_text, re.IGNORECASE)
    if m_dia:
        data_leilao = m_dia.group(1).strip()

    artista = ""
    for strong in td_data.find_all("strong"):
        txt = strong.get_text(strip=True)
        if txt and ":" not in txt and re.search(r"[A-Z\xc1\xc9\xcd\xd3\xda\xc2\xca\xce\xd4\xdb\xc3\xd5\xc0\xdc\xc7]", txt):
            if not re.match(r"Lote\s+N", txt, re.IGNORECASE):
                artista = txt
                break

    campos = {}
    for strong in td_data.find_all("strong"):
        label = strong.get_text(strip=True)
        if label.endswith(":"):
            label_clean = label[:-1].strip()
            next_sib = strong.next_sibling
            valor_txt  = ""
            while next_sib:
                if hasattr(next_sib, "get_text"):
                    t = next_sib.get_text(strip=True)
                    if t:
                        valor_txt = t
                        break
                elif isinstance(next_sib, str):
                    t = next_sib.strip()
                    if t:
                        valor_txt = t
                        break
                next_sib = getattr(next_sib, "next_sibling", None)
            campos[label_clean] = valor_txt

    titulo    = campos.get("T\xedtulo",   campos.get("Titulo",    ""))
    tecnica   = campos.get("T\xe9cnica",  campos.get("Tecnica",   ""))
    tiragem   = campos.get("Tiragem",   "")
    medidas   = campos.get("Medidas",   "")
    assinado  = campos.get("Assinado",  "")
    data_obra = campos.get("Data/Local", campos.get("Data", ""))

    skip = {"T\xedtulo","Titulo","T\xe9cnica","Tecnica","Tiragem","Medidas","Assinado","Data/Local","Data"}
    desc_parts = [f"{k}: {v}" for k, v in campos.items() if k not in skip and v]
    descricao_extra = "; ".join(desc_parts)

    verbete_url = ""
    for a in td_data.find_all("a"):
        href = a.get("href", "")
        if "verbete" in href:
            verbete_url = BASE_URL + "/leilao/" + href

    if not artista and not titulo:
        return None

    return {
        "lote_num":        lote_num,
        "artista":         artista,
        "titulo":          titulo,
        "tecnica":         tecnica,
        "tiragem":         tiragem,
        "medidas":         medidas,
        "assinado":        assinado,
        "data_obra":       data_obra,
        "valor_base":      valor_base,
        "lance_atual":     lance_atual,
        "tipo_lance":      tipo_lance,
        "data_leilao":     data_leilao,
        "img_thumb":       img_url_thumb,
        "img_grande":      img_url_grande,
        "url_lote":        LOTE_URL.format(n=n),
        "verbete_url":     verbete_url,
        "descricao_extra": descricao_extra,
        "coletado_em":     datetime.now().isoformat(),
    }


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Tableau Arte & Leiloes - Coleta de Catalogo")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Leilao: 24-26/03/2026")
    print()

    session = requests.Session()
    lotes  = []
    vazios = 0
    ok = 0

    for n in range(1, 601):
        url = LOTE_URL.format(n=n)
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                dados = parse_lote(r.content, n)
                if dados:
                    lotes.append(dados)
                    ok += 1
                    vazios = 0
                    print(f"  {n:4d}: {dados['artista'][:40]:<40} | {dados['titulo'][:30]:<30} | R$ {dados['valor_base']}")
                else:
                    vazios += 1
                    print(f"  {n:4d}: [vazio]")
            else:
                vazios += 1
        except Exception as e:
            vazios += 1
            print(f"  {n:4d}: ERRO {e}")

        if vazios >= MAX_VAZIOS:
            print(f"\n>>> {MAX_VAZIOS} vazios consecutivos. Parando em lote {n}.")
            break

        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"Total coletados: {ok} lotes")

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(lotes, f, ensure_ascii=False, indent=2)
    print(f"JSON salvo: {DB_FILE}")

    try:
        import pandas as pd
        df = pd.DataFrame(lotes)
        colunas = ["lote_num","artista","titulo","tecnica","tiragem","medidas","assinado",
                   "data_obra","valor_base","lance_atual","tipo_lance","data_leilao",
                   "img_thumb","img_grande","url_lote","verbete_url","descricao_extra","coletado_em"]
        colunas_ok = [c for c in colunas if c in df.columns]
        df[colunas_ok].to_excel(XLSX_FILE, index=False)
        print(f"Excel salvo: {XLSX_FILE}")
    except Exception as e:
        print(f"Erro Excel: {e}")

    valores = [l["valor_base"] for l in lotes if l.get("valor_base")]
    if valores:
        print(f"\nValor minimo: R$ {min(valores):,.2f}")
        print(f"Valor maximo: R$ {max(valores):,.2f}")
        print(f"Valor medio:  R$ {sum(valores)/len(valores):,.2f}")

    tecs = Counter(l["tecnica"].lower() for l in lotes if l.get("tecnica"))
    print(f"\nTop tecnicas:")
    for tec, cnt in tecs.most_common(12):
        print(f"  {cnt:3d}x {tec}")

    return lotes


if __name__ == "__main__":
    lotes = main()
    print(f"\nFinalizado: {len(lotes)} lotes no total.")
