#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, time, re, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
})

CANDIDATOS = {
    "Antiquário Na Vovó":       "www.navovotem.com.br",
    "Antiquário Brexo":         "www.brexodolucio.com.br",
    "Atenas Antiquário":        "www.leilaoatenas.com.br",
    "Beto Assef":               "www.betoassef.com.br",
    "Felix Conrado":            "www.conradoleiloeiro.com.br",
    "Imperial JM":              "www.jotamleiloes.com.br",
    "Leilões Dutra":            "www.antiquariodutraqueimados.com.br",
    "Leilões Paulão":           "www.paulaoantiguidades.com.br",
    "Miguel Salles":            "www.miguelsalles.com.br",
    "VM Escritório de Arte":    "www.vmescritarteleiloes.com.br",
    "Velho que Vale":           "www.rachelnahon.com.br",
}

print(f"{'Casa':<30} {'Domínio':<45} {'Status'}")
print("-" * 90)
confirmados = {}

for nome, dom in CANDIDATOS.items():
    try:
        r = session.get(f"http://{dom}/catalogo.asp", timeout=10, allow_redirects=True)
        lotes = len(re.findall(r'peca\.asp\?Id=\d+', r.text))
        is_v89 = "V8.9" in r.text or "leiloesbr" in r.text.lower() or lotes > 0
        status = f"OK  ({lotes} lotes)" if is_v89 else f"200 mas não V8.9"
        if is_v89:
            confirmados[nome] = f"http://{dom}"
        print(f"  {nome:<28} {dom:<45} {status}")
    except Exception as e:
        print(f"  {nome:<28} {dom:<45} ERRO: {type(e).__name__}")
    time.sleep(0.5)

print(f"\nConfirmados: {len(confirmados)}/{len(CANDIDATOS)}")
if confirmados:
    print("\nPara V89_HOUSES:")
    for nome, url in confirmados.items():
        print(f'    "{url}",  # {nome}')
