#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, time, re, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
})

def testa_url(url):
    try:
        r = session.get(url, timeout=8, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 300:
            lotes = len(re.findall(r'peca\.asp\?Id=\d+', r.text))
            is_v89 = "V8.9" in r.text or "leiloesbr" in r.text.lower() or lotes > 0
            return is_v89, lotes, r.url
    except Exception:
        pass
    return False, 0, ""

CANDIDATOS = {
    "Antiquário Na Vovó": [
        "antiquarionavovo.lel.br", "navovo.lel.br", "antiquariovovo.lel.br",
        "antiquariovovo.com.br", "navovoleiloes.lel.br", "antiquariovovo.lel.br",
        "antiquarionavovo.com.br", "avovo.lel.br",
    ],
    "Antiquário Brexo do Lúcio": [
        "brexo.lel.br", "antiquariobrexo.lel.br", "brexodolucio.lel.br",
        "brexoleiloes.lel.br", "brexo.com.br", "luciobrexo.lel.br",
        "antiquarioluciobr.lel.br",
    ],
    "Atenas Antiquário": [
        "atenas.lel.br", "atenasantiquario.lel.br", "atenasantiguidades.lel.br",
        "atenasantiquario.com.br", "atenasantiguidades.com.br", "atenasleiloes.com.br",
        "atenasantiquariocasadeleiloes.com.br",
    ],
    "Beto Assef": [
        "betoassef.lel.br", "betoassefleloeiro.lel.br", "betoassefleloeiro.com.br",
        "betoassefleiloes.com.br", "betoleiloeiro.com.br", "assefleloeiro.lel.br",
    ],
    "Casa Paladino": [
        "casapaladino.lel.br", "paladino.lel.br", "casapaladinoleiloes.lel.br",
        "casapaladinoleiloes.com.br", "paladino.com.br", "casapaladino.com.br",
    ],
    "Felix Conrado": [
        "felixconrado.lel.br", "felixconradoleloeiro.lel.br", "felixconradoleiloeiro.com.br",
        "felixconradoleiloes.com.br", "fconrado.lel.br", "conrado.lel.br",
    ],
    "Imperial JM Leilões": [
        "imperialjm.lel.br", "imperialjmleiloes.lel.br", "imperialjm.com.br",
        "imperialjmleiloes.com.br", "imperialleiloesJM.com.br", "jmleiloes.com.br",
        "imperialJMleiloes.lel.br",
    ],
    "Leilão do Cacareco": [
        "cacareco.lel.br", "leilaocacareco.lel.br", "cacarecoantigualeiloes.lel.br",
        "cacarecoantigualeiloes.com.br", "leilaodocacareco.com.br",
        "cacarecoantigual.com.br",
    ],
    "Leilões Dutra Queimados": [
        "dutra.lel.br", "dutraleiloes.lel.br", "leiloesdutra.lel.br",
        "leiloesdutra.com.br", "dutraqueimados.lel.br", "dutraqueimadosleiloes.com.br",
        "dutraleiloes.com.br",
    ],
    "Leilões Paulão": [
        "paulao.lel.br", "leiloespaulao.lel.br", "paulaoleiloes.lel.br",
        "paulaoleiloes.com.br", "paulaoantigualeiloes.com.br",
        "leilaopaulao.com.br",
    ],
    "Miguel Salles": [
        "miguelsalles.lel.br", "miguelsallesleiloes.lel.br", "miguelsallesarte.lel.br",
        "miguelsallesarte.com.br", "escritoriomiguelsalles.com.br",
        "miguelsallesescritoriodearte.com.br",
    ],
    "Reginaldo da Costa": [
        "reginaldo.lel.br", "reginaldodacosta.lel.br", "reginaldoleiloes.lel.br",
        "reginaldocostaleiloes.com.br", "reginaldoleiloes.com.br",
        "reginaldodacostaleiloes.com.br",
    ],
    "Suyane Serra": [
        "suyane.lel.br", "suyaneserra.lel.br", "suyaneleiloeira.lel.br",
        "suyaneserra.com.br", "suyaneleiloeira.com.br", "suyaneserraleiloes.com.br",
    ],
    "VM Escritório de Arte": [
        "vmescritorio.lel.br", "vmescritoriodearte.lel.br", "vmarte.lel.br",
        "vmescritoriodearte.com.br", "vmarte.com.br", "vmescritorioarte.com.br",
        "vmescritoriodarte.lel.br",
    ],
    "Velho que Vale": [
        "velhoquevale.lel.br", "velhoquevaleantiguidades.lel.br",
        "velhoquevaleantiguidades.com.br", "velhoquevale.com.br",
        "velhocomvale.lel.br", "vqvleiloes.com.br",
    ],
}

print("Testando domínios das 15 casas restantes...\n")
encontrados = {}

for nome, dominios in CANDIDATOS.items():
    achou = False
    for dom in dominios:
        ok, lotes, final_url = testa_url(f"http://www.{dom}/catalogo.asp")
        if ok:
            print(f"  ✓ {nome:<40} -> {dom}  ({lotes} lotes)")
            encontrados[nome] = f"http://www.{dom}"
            achou = True
            break
        time.sleep(0.3)
    if not achou:
        # Tenta sem www
        for dom in dominios:
            ok, lotes, final_url = testa_url(f"http://{dom}/catalogo.asp")
            if ok:
                print(f"  ✓ {nome:<40} -> {dom}  ({lotes} lotes)")
                encontrados[nome] = f"http://{dom}"
                achou = True
                break
            time.sleep(0.2)
    if not achou:
        print(f"  ✗ {nome:<40} -> não encontrado")

print(f"\n\nEncontrados: {len(encontrados)}/{len(CANDIDATOS)}")
if encontrados:
    print("\nPara adicionar ao V89_HOUSES:")
    for nome, url in sorted(encontrados.items()):
        print(f'    "{url}",  # {nome}')
