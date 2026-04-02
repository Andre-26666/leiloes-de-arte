#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catálogo Tableau Arte & Leilões
Coleta todos os lotes do leilão atual em www.tableau.com.br
Saída: tableau_db.json  e  tableau_leilao_analise.xlsx
"""

import sys, io, os, json, re, time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

# ── Caminhos ──────────────────────────────────────────────────────────────────
_DIR        = os.path.dirname(os.path.abspath(__file__))
DB_FILE     = os.path.join(_DIR, "tableau_db.json")
CKPT_FILE   = os.path.join(_DIR, "tableau_checkpoint.json")
OUTPUT_XLSX = os.path.join(_DIR, "tableau_leilao_analise.xlsx")
LOG_FILE    = os.path.join(_DIR, "tableau_log.txt")

# ── Configurações ─────────────────────────────────────────────────────────────
BASE_URL    = "https://www.tableau.com.br"
LOTE_URL    = BASE_URL + "/leilao/lote.php?lote={n}"
IMG_BASE    = BASE_URL + "/leilao/"
DELAY       = 0.8     # segundos entre requisições
MAX_LOTE    = 600     # máximo para busca
MAX_VAZIOS  = 15      # lotes vazios consecutivos antes de parar

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_valor(texto):
    """Extrai valor numérico de string como 'R$ 1.500,00'"""
    if not texto:
        return None
    m = re.search(r'R\$\s*([\d.,]+)', texto)
    if m:
        v = m.group(1).replace('.', '').replace(',', '.')
        try:
            return float(v)
        except:
            return None
    return None

def parse_lote(html_content, n):
    """Faz parsing do HTML de um lote e retorna dict com dados."""
    soup = BeautifulSoup(html_content, 'lxml')

    # Remove scripts/styles
    for tag in soup(['script', 'style']):
        tag.decompose()

    table = soup.find('table')
    if not table:
        return None

    tds = table.find_all('td')
    if len(tds) < 2:
        return None

    # TD[0] = imagem | TD[1] = dados
    td_img  = tds[0]
    td_data = tds[1] if len(tds) > 1 else None

    if not td_data:
        return None

    # ── Imagem ────────────────────────────────────────────────────────────────
    img_tag = td_img.find('img')
    img_src = img_tag.get('src', '') if img_tag else ''
    # Construir URL completa da imagem grande
    if img_src:
        base_img = img_src.replace('.jpg', '').replace('p.jpg', '')
        img_url_thumb = IMG_BASE + img_src
        # Versão grande (sufixo 'g')
        img_nome = img_src.replace('.jpg', 'g.jpg')
        img_url_grande = IMG_BASE + img_nome
    else:
        img_url_thumb = ''
        img_url_grande = ''

    # ── Texto principal ───────────────────────────────────────────────────────
    full_text = td_data.get_text(separator='\n', strip=True)

    # Verificar se lote tem dados reais
    if not full_text or 'ALDEMIR' not in full_text and len(full_text) < 30:
        # Verifica se há artista na primeira strong
        strongs = td_data.find_all('strong')
        if not strongs or all(s.get_text(strip=True) == '' for s in strongs):
            return None

    # ── Número e tipo de lance ────────────────────────────────────────────────
    lote_num = n
    tipo_lance = ''
    m_lote = re.search(r'Lote\s+N[ºo°]?\s*(\d+)\s*[-–]\s*([^\n]+)', full_text, re.IGNORECASE)
    if m_lote:
        lote_num = int(m_lote.group(1))
        tipo_lance = m_lote.group(2).strip()

    # ── Valor base/lance atual ────────────────────────────────────────────────
    valor_base = None
    lance_atual = None

    m_oferta = re.search(r'Temos oferta de:\s*R\$\s*([\d.,]+)', full_text, re.IGNORECASE)
    if m_oferta:
        v = m_oferta.group(1).replace('.', '').replace(',', '.')
        try:
            lance_atual = float(v)
            valor_base  = lance_atual  # sem info separada, assume igual
        except:
            pass

    m_aguardando = re.search(r'Aguardando oferta', full_text, re.IGNORECASE)
    if m_aguardando and not lance_atual:
        lance_atual = 0.0

    # ── Data do leilão ────────────────────────────────────────────────────────
    data_leilao = ''
    m_dia = re.search(r'Dia do Leil[ãa]o:\s*([^\n]+)', full_text, re.IGNORECASE)
    if m_dia:
        data_leilao = m_dia.group(1).strip()

    # ── Artista ───────────────────────────────────────────────────────────────
    artista = ''
    # Primeiro <strong> com letras maiúsculas sem ":" é o artista
    for strong in td_data.find_all('strong'):
        txt = strong.get_text(strip=True)
        if txt and ':' not in txt and re.search(r'[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÜÇ]', txt):
            # Descarta "Lote Nº..."
            if not re.match(r'Lote\s+N', txt, re.IGNORECASE):
                artista = txt
                break

    # Fallback: linha com nome em maiúsculas após os formulários
    if not artista:
        paragrafos = td_data.find_all('p')
        for p in paragrafos:
            strongs = p.find_all('strong')
            for s in strongs:
                txt = s.get_text(strip=True)
                if txt and ':' not in txt and txt.upper() == txt and len(txt) > 3:
                    if not re.match(r'Lote', txt, re.IGNORECASE):
                        artista = txt
                        break
            if artista:
                break

    # ── Campos label:valor ────────────────────────────────────────────────────
    campos = {}
    # Percorre nós de texto após <strong>label:</strong>
    for strong in td_data.find_all('strong'):
        label = strong.get_text(strip=True)
        if label.endswith(':'):
            label_clean = label[:-1].strip()
            # Próximo texto após o strong
            next_sib = strong.next_sibling
            valor_txt = ''
            while next_sib:
                if hasattr(next_sib, 'get_text'):
                    t = next_sib.get_text(strip=True)
                    if t:
                        valor_txt = t
                        break
                elif isinstance(next_sib, str):
                    t = next_sib.strip()
                    if t:
                        valor_txt = t
                        break
                next_sib = next_sib.next_sibling if hasattr(next_sib, 'next_sibling') else None
            campos[label_clean] = valor_txt

    titulo    = campos.get('Título', campos.get('Titulo', ''))
    tecnica   = campos.get('Técnica', campos.get('Tecnica', ''))
    tiragem   = campos.get('Tiragem', '')
    medidas   = campos.get('Medidas', '')
    assinado  = campos.get('Assinado', '')
    data_obra = campos.get('Data/Local', campos.get('Data', ''))

    # Sem artista = lote inválido/vazio
    if not artista and not titulo:
        return None

    # ── Descrição completa ────────────────────────────────────────────────────
    desc_parts = []
    for k, v in campos.items():
        if k not in ('Título', 'Titulo', 'Técnica', 'Tecnica', 'Tiragem',
                     'Medidas', 'Assinado', 'Data/Local', 'Data'):
            desc_parts.append(f"{k}: {v}")
    descricao_extra = '; '.join(desc_parts)

    # ── Link verbete (autor) ──────────────────────────────────────────────────
    verbete_link = ''
    for a in td_data.find_all('a'):
        href = a.get('href', '')
        if 'verbete' in href:
            verbete_link = BASE_URL + '/leilao/' + href

    # ── Montar resultado ──────────────────────────────────────────────────────
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
        "verbete_url":     verbete_link,
        "descricao_extra": descricao_extra,
        "coletado_em":     datetime.now().isoformat(),
    }

# ── Fetch com retry ───────────────────────────────────────────────────────────
def fetch(url, session, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                # Força encoding correto — tableau.com.br serve latin-1/iso-8859-1
                r.encoding = r.apparent_encoding or "iso-8859-1"
                return r.text
            elif r.status_code == 404:
                return None
        except Exception as e:
            log(f"  Erro ao buscar {url}: {e} (tentativa {attempt+1})")
            time.sleep(2)
    return None

# ── Coleta principal ──────────────────────────────────────────────────────────
def coletar_lotes(inicio=1, fim=MAX_LOTE):
    session = requests.Session()
    lotes = []
    vazios_consecutivos = 0
    total_coletados = 0
    total_pulados = 0

    log(f"Iniciando coleta: lotes {inicio} a {fim}")
    log(f"URL base: {LOTE_URL.format(n='N')}")

    for n in range(inicio, fim + 1):
        url = LOTE_URL.format(n=n)
        content = fetch(url, session)

        if content is None:
            log(f"  Lote {n:4d}: 404 — pulando")
            vazios_consecutivos += 1
            total_pulados += 1
        else:
            dados = parse_lote(content, n)
            if dados:
                lotes.append(dados)
                total_coletados += 1
                vazios_consecutivos = 0
                log(f"  Lote {n:4d}: {dados['artista'][:35]:<35} | {dados['titulo'][:30]:<30} | R$ {dados['valor_base']}")
            else:
                vazios_consecutivos += 1
                total_pulados += 1
                log(f"  Lote {n:4d}: sem dados válidos")

        # Salva checkpoint a cada 50 lotes
        if n % 50 == 0:
            with open(CKPT_FILE, 'w', encoding='utf-8') as f:
                json.dump({"ultimo_lote": n, "total_coletados": total_coletados, "lotes": lotes}, f, ensure_ascii=False, indent=2)
            log(f"  >> Checkpoint salvo (lote {n}, {total_coletados} coletados)")

        if vazios_consecutivos >= MAX_VAZIOS:
            log(f"  {MAX_VAZIOS} lotes vazios consecutivos — encerrando em lote {n}")
            break

        time.sleep(DELAY)

    log(f"\nColeta concluída: {total_coletados} lotes coletados, {total_pulados} pulados")
    return lotes

# ── Exportação ────────────────────────────────────────────────────────────────
def exportar_xlsx(lotes):
    try:
        import pandas as pd
        df = pd.DataFrame(lotes)
        # Reordena colunas
        colunas = [
            'lote_num', 'artista', 'titulo', 'tecnica', 'tiragem',
            'medidas', 'assinado', 'data_obra', 'valor_base', 'lance_atual',
            'tipo_lance', 'data_leilao', 'img_thumb', 'img_grande',
            'url_lote', 'verbete_url', 'descricao_extra', 'coletado_em'
        ]
        colunas_existentes = [c for c in colunas if c in df.columns]
        df = df[colunas_existentes]
        df.to_excel(OUTPUT_XLSX, index=False)
        log(f"Excel salvo: {OUTPUT_XLSX} ({len(df)} linhas)")
    except Exception as e:
        log(f"Erro ao exportar Excel: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("TABLEAU ARTE & LEILÕES — Coleta de Catálogo")
    log(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log("=" * 60)

    # Verifica checkpoint existente
    inicio = 1
    lotes_existentes = []
    if os.path.exists(CKPT_FILE):
        try:
            with open(CKPT_FILE, 'r', encoding='utf-8') as f:
                ckpt = json.load(f)
            ultimo = ckpt.get('ultimo_lote', 0)
            lotes_existentes = ckpt.get('lotes', [])
            if ultimo > 0 and lotes_existentes:
                resposta = input(f"Checkpoint encontrado (último lote: {ultimo}, {len(lotes_existentes)} lotes). Continuar? [s/N]: ").strip().lower()
                if resposta == 's':
                    inicio = ultimo + 1
                    log(f"Continuando do lote {inicio}")
                else:
                    lotes_existentes = []
                    log("Iniciando do zero")
        except:
            pass

    novos_lotes = coletar_lotes(inicio=inicio)
    todos_lotes = lotes_existentes + novos_lotes

    # Deduplica por lote_num
    seen = set()
    lotes_unicos = []
    for l in todos_lotes:
        k = l['lote_num']
        if k not in seen:
            seen.add(k)
            lotes_unicos.append(l)
    lotes_unicos.sort(key=lambda x: x['lote_num'])

    # Salva JSON
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(lotes_unicos, f, ensure_ascii=False, indent=2)
    log(f"JSON salvo: {DB_FILE} ({len(lotes_unicos)} lotes)")

    # Exporta Excel
    exportar_xlsx(lotes_unicos)

    # Remove checkpoint após conclusão
    if os.path.exists(CKPT_FILE):
        os.remove(CKPT_FILE)

    log("\n=== RESUMO FINAL ===")
    log(f"Total de lotes coletados: {len(lotes_unicos)}")
    if lotes_unicos:
        valores = [l['valor_base'] for l in lotes_unicos if l.get('valor_base')]
        if valores:
            log(f"Valor base mínimo: R$ {min(valores):,.2f}")
            log(f"Valor base máximo: R$ {max(valores):,.2f}")
            log(f"Valor base médio:  R$ {sum(valores)/len(valores):,.2f}")

    # Sincroniza com Supabase
    try:
        import supabase_sync
        if supabase_sync.enabled():
            log("Sincronizando com Supabase...")
            supabase_sync.sync_tableau(lotes_unicos)
    except Exception as _e:
        log(f"[supabase] aviso: {_e}")

    return lotes_unicos

if __name__ == '__main__':
    lotes = main()
    # Imprime JSON final para stdout se quiser capturar
    # print(json.dumps(lotes, ensure_ascii=False, indent=2))
