#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Busca os domínios das casas da lista de clientes LeiloesBR
testando URLs comuns a partir do nome da casa.
"""
import sys, time, re, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
})

# Casas ainda não encontradas — testamos possíveis domínios
CANDIDATOS = {
    "Antiquariato Leilões":    ["antiquariato.lel.br", "antiquariatoleiloes.com.br", "antiquariato.com.br"],
    "Antiquário Na Vovó":      ["navovoleiloes.com.br", "antiquariovovo.com.br", "navovoantigualeiloes.com.br"],
    "Antiquário Brexo":        ["brexo.lel.br", "antiquariobrexo.com.br", "brexoleiloes.com.br"],
    "Antiquário Fundo do Baú": ["fundodobau.lel.br", "fundodobauleiloes.com.br", "antiquariofundodobau.com.br"],
    "Antiquário Ibiza":        ["antiquarioibiza.lel.br", "antiquarioibiza.com.br", "ibizaantiquario.com.br"],
    "Arte Maior Leilões":      ["artemaior.lel.br", "artemaiorleiloes.com.br", "artemaior.com.br"],
    "Arte Moderna Leilões":    ["artemodernaleloes.lel.br", "artemodernaleiloes.com.br", "artemoderna.lel.br"],
    "Atenas Antiquário":       ["atenas.lel.br", "atenasantiquario.com.br", "atenasantiguidades.com.br"],
    "Bahia Leilões":           ["bahialeiloes.lel.br", "bahialeiloes.com.br", "bahia.lel.br"],
    "Beto Assef":              ["betoassef.lel.br", "betoassefleloeiro.com.br", "betoassefleiloes.com.br"],
    "Braz Coleção":            ["braz.lel.br", "brazcolecao.com.br", "braz-colecao.com.br"],
    "Casa Brasileira":         ["casabrasileira.lel.br", "casabrasileiraleiloes.com.br", "casabrasileiraorg.com.br"],
    "Casa Lu Maria":           ["casalumaria.lel.br", "casalumarialeiloes.com.br", "lumaria.lel.br"],
    "Casa Paladino":           ["casapaladino.lel.br", "casapaladinoleiloes.com.br", "paladino.lel.br"],
    "Cohen Leilões":           ["cohenleiloes.lel.br", "cohenleiloes.com.br", "cohen.lel.br"],
    "Daniel Chaieb":           ["chaieb.lel.br", "danielchaieb.com.br", "danielchaiebleiloeiro.com.br"],
    "Felix Conrado":           ["felixconrado.lel.br", "felixconradoleiloeiro.com.br", "felixconrado.com.br"],
    "Galpão dos Leilões":      ["galpaodosleiloes.lel.br", "galpao.lel.br", "galpaoleiloes.com.br"],
    "Imperial JM":             ["imperialjm.lel.br", "imperialleiloes.com.br", "imperialjmleiloes.com.br"],
    "Leilão do Cacareco":      ["cacareco.lel.br", "leilaocacareco.com.br", "cacarecoantigualeiloes.com.br"],
    "Leilões Dutra":           ["dutraleiloes.lel.br", "leiloesdutra.com.br", "dutra.lel.br"],
    "Leilões Nova Era":        ["novaera.lel.br", "leiloesnovaera.com.br", "novaeraleoes.com.br"],
    "Leilões Paulão":          ["paulao.lel.br", "leiloespaulao.com.br", "paulaoleiloes.com.br"],
    "Linha do Tempo":          ["linhadotempo.lel.br", "linhadotempoantiguidades.com.br", "linhatempo.lel.br"],
    "Lipe Mobiliário":         ["lipe.lel.br", "lipemobiliario.com.br", "lipeleiloes.com.br"],
    "Marrakech":               ["marrakech.lel.br", "marrakechleiloes.com.br", "marrakechantique.com.br"],
    "Miguel Salles":           ["miguelsalles.lel.br", "miguelsallesleiloes.com.br", "miguelsallesarte.com.br"],
    "Mundo em Artes":          ["mundoenartes.lel.br", "mundoenartes.com.br", "mundoemartes.com.br"],
    "Nárnia Leilões":          ["narnia.lel.br", "narnialeiloes.com.br", "narnia.com.br"],
    "RT Leilões":              ["rtleiloes.com.br", "rt.lel.br", "rtleiloesearte.com.br"],
    "Recanto das Artes":       ["recanto.lel.br", "recantodasartes.com.br", "recantoartes.lel.br"],
    "Reginaldo da Costa":      ["reginaldo.lel.br", "reginaldocostaleiloes.com.br", "reginaldodacosta.lel.br"],
    "Rio de Janeiro Leilões":  ["rjleiloes.lel.br", "riodejaneiroleiloes.com.br", "rdleiloes.com.br"],
    "Robson Gini":             ["robsongini.lel.br", "robsonginileiloes.com.br", "tremdas7.com.br"],
    "Sergio Altit":            ["altit.lel.br", "sergioaltit.com.br", "sergioaltitleiloes.com.br"],
    "Suyane Serra":            ["suyane.lel.br", "suyaneserra.com.br", "suyanelerroeiro.com.br"],
    "São Bento Leilões":       ["saobento.lel.br", "saobentoleloes.com.br", "saobentoleiloes.com.br"],
    "Taty Paschoal":           ["tatypaschoal.lel.br", "tatypaschoalleiloes.com.br", "tatypaschoal.com.br"],
    "Urca Leilões":            ["urcaleiloes.lel.br", "urcaleiloes.com.br", "urca.lel.br"],
    "VM Escritório de Arte":   ["vmescritorio.lel.br", "vmescritoriodearte.com.br", "vmarte.com.br"],
    "Velho que Vale":          ["velhoquevale.lel.br", "velhoquevale.com.br", "velhoquevaleantiguidades.com.br"],
}

print("Testando domínios candidatos...\n")
encontrados = {}

for nome, urls in CANDIDATOS.items():
    achou = False
    for url in urls:
        test_url = f"http://www.{url}/catalogo.asp"
        try:
            r = session.get(test_url, timeout=8, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                # Verifica se é plataforma V8.9
                is_v89 = "V8.9" in r.text or "leiloesbr" in r.text.lower() or "peca.asp" in r.text.lower()
                lotes = len(re.findall(r'peca\.asp\?Id=\d+', r.text))
                if is_v89 or lotes > 0:
                    print(f"  ✓ {nome:<35} -> {url}  ({lotes} lotes)")
                    encontrados[nome] = f"http://www.{url}"
                    achou = True
                    break
                else:
                    print(f"  ? {nome:<35} -> {url} (200 mas não V8.9)")
                    achou = True
                    break
        except Exception:
            pass
        time.sleep(0.3)
    if not achou:
        print(f"  ✗ {nome:<35} -> não encontrado")

print(f"\n\nEncontrados: {len(encontrados)}/{len(CANDIDATOS)}")
print("\nPara adicionar ao V89_HOUSES:")
for nome, url in sorted(encontrados.items()):
    print(f'    "{url}",  # {nome}')
