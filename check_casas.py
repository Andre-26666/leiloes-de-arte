#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, time, re, requests, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
})

FALTANDO = [
    "Acervo Leiloes",
    "Alberto Lopes Leiloeiro",
    "Antigo Moderno Leiloes",
    "Antiquariato Leiloes",
    "Antiquario Vovo",
    "Antiquario Brexo",
    "Fundo do Bau",
    "Antiquario Ibiza",
    "La Vie En Rose Leiloes",
    "Arte Maior Leiloes",
    "Arte Moderna Leiloes",
    "Atenas Antiquario",
    "Bahia Leiloes",
    "Beto Assef",
    "Bradg Design Gallery",
    "Casa Brasileira Leiloes",
    "Casa Lu Maria Leiloes",
    "Casa Paladino Leiloes",
    "Cohen Leiloes",
    "Daniel Chaieb",
    "Felix Conrado",
    "Galpao dos Leiloes",
    "Imperial JM Leiloes",
    "Leilao do Cacareco",
    "Leiloes Dutra",
    "Leiloes Lemos",
    "Leiloes Nova Era",
    "Leiloes Paulao",
    "Linha do Tempo Antiguidades",
    "Marcio Pinho Leiloeiro",
    "Marrakech Antique",
    "Miguel Salles Arte",
    "Mundo em Artes Leiloes",
    "Narnia Leiloes",
    "RR DECO",
    "RT Leiloes",
    "Recanto das Artes Leiloes",
    "Reginaldo da Costa Leiloes",
    "Rio de Janeiro Leiloes",
    "Robson Gini Leiloes",
    "Santayana Leiloes",
    "Sergio Altit Leiloes",
    "Subdistrito Leiloes",
    "Suyane Serra Leiloes",
    "Sao Bento Leiloes",
    "Taty Paschoal Leiloes",
    "Urca Leiloes",
    "VM Escritorio Arte",
    "Velho que Vale",
]

BASE = "https://www.leiloesbr.com.br"
resultado = {}

for nome in FALTANDO:
    params = {"pesquisa": nome, "op": "1", "v": "20", "b": "0", "gbl": "0", "tp": "|"}
    try:
        r = session.get(f"{BASE}/busca_andamento.asp", params=params, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        domains = set()
        for a in soup.find_all("a", href=re.compile(r"abre_catalogo")):
            m = re.search(r'abre_catalogo\.asp\?t=1\|(https?://[^|]+)\|', a.get("href",""))
            if m:
                dom = re.sub(r'^https?://(www\.)?', '', m.group(1)).rstrip('/')
                domains.add(dom)
        cnt = len(domains)
        if cnt:
            resultado[nome] = sorted(domains)
            print(f"  INDEXADO  {nome:<35} -> {', '.join(sorted(domains))}")
        else:
            print(f"  SEM LOTE  {nome:<35}")
    except Exception as e:
        print(f"  ERRO      {nome:<35} -> {e}")
    time.sleep(1.0)

# buscar tambem nos finalizados para ver dominio
print("\n--- Verificando nos finalizados ---")
for nome, doms in resultado.items():
    print(f"  {nome}: {doms}")

with open("check_casas_result.json", "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)
print("\nResultado salvo em check_casas_result.json")
