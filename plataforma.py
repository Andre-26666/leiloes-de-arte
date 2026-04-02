#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plataforma de Arte — Leilões & Histórico de Preços
Execute com:  streamlit run plataforma.py --server.address localhost
"""

import base64
import hashlib

import json
import os
import re as _re
import unicodedata as _ud

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Supabase ─────────────────────────────────────────────────────────────────
def _get_supabase():
    """Retorna cliente Supabase se configurado, senão None."""
    url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None

_SB = _get_supabase()
_USE_SUPABASE = _SB is not None


def _norm_art(s):
    """Normaliza nome de artista para comparação: maiúsculas, sem acentos, sem preposições."""
    s = _re.sub(r'\(.*?\)', '', s or '').strip()
    nfkd = _ud.normalize('NFKD', s.upper())
    s = ''.join(c for c in nfkd if not _ud.combining(c))
    return _re.sub(r'\s+', ' ', _re.sub(r'[^A-Z\s]', '', s)).strip()

# ── Autenticação ────────────────────────────────────────────────────────────────
# Para alterar a senha: python -c "import hashlib; print(hashlib.sha256('SUASENHA'.encode()).hexdigest())"
_SENHA_HASH = "8ec14bfb6e39a45f4ed93b16b075f4b1fb8fd47093830b6e720898a80a64fbd5"  # arte2026

def _tela_login():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400&family=Inter:wght@400;500&display=swap');
    [data-testid="stAppViewContainer"] { background: #eef3f7; }
    [data-testid="stSidebar"] { display: none; }
    .login-box {
        max-width: 380px; margin: 8vh auto 0;
        background: #ffffff; border: 1px solid #b8d0de;
        border-radius: 16px; padding: 48px 40px 40px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.08);
    }
    .login-logo { font-size: 2.4rem; text-align: center; margin-bottom: 6px; }
    .login-title {
        font-family: 'Cormorant Garamond', serif;
        color: #4a8fa8; font-size: 1.5rem; font-weight: 300;
        text-align: center; letter-spacing: .1em;
        text-transform: uppercase; margin-bottom: 28px;
    }
    </style>
    <div class="login-box">
      <div class="login-logo">🖼️</div>
      <div class="login-title">Art Radar</div>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        senha = st.text_input("Senha", type="password", placeholder="••••••••", label_visibility="collapsed")
        if st.button("Entrar", use_container_width=True):
            if hashlib.sha256(senha.encode()).hexdigest() == _SENHA_HASH:
                st.session_state["_auth"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()

if not st.session_state.get("_auth"):
    _tela_login()

_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_FILE  = os.path.join(_DIR, "leiloesbr_db.json")
CDA_FILE = os.path.join(_DIR, "cda_db.json")
BDA_FILE = os.path.join(_DIR, "bolsadearte_db.json")
ARR_FILE = os.path.join(_DIR, "arrematearte_db.json")
TAB_FILE = os.path.join(_DIR, "tableau_db.json")
HCF_FILE     = os.path.join(_DIR, "historico_casas_db.json")  # Levy + Conrad histórico
VISUAL_INDEX = os.path.join(_DIR, "visual_index.json")

# ── Página ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Art Radar",
    page_icon="🎯",
    layout="wide",
)

# ── Fundo hero ────────────────────────────────────────────────────────────────
def _b64_img(filename: str) -> str:
    path = os.path.join(_DIR, filename)
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""

_FUNDO_B64 = _b64_img("fundo.png")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Inter:wght@300;400;500;600&display=swap');

/* ── Paleta ──────────────────────────────────────────────────
   Fundo: creme quente  #eef3f7
   Card:  branco        #ffffff
   Texto: carvão        #1a2a35
   Texto 2: castanho    #3a5a6e
   Borda: bege          #b8d0de
   Destaque: ouro       #4a8fa8
   ─────────────────────────────────────────────────────────── */

/* ── Reset & base ── */
[data-testid="stAppViewContainer"] {
    background: #eef3f7;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #dde8f0 !important; }
section[data-testid="stMain"] > div { padding-top: 0 !important; }
.block-container { padding: 0 2rem 2rem 2rem !important; max-width: 1400px; }

/* ── Hero header ── */
.hero {
    position: relative;
    width: 100%;
    height: 220px;
    border-radius: 0 0 20px 20px;
    overflow: hidden;
    margin-bottom: 2rem;
    background-size: cover;
    background-position: center 30%;
}
.hero-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        to bottom,
        rgba(200,220,235,0.08) 0%,
        rgba(210,228,240,0.45) 60%,
        rgba(220,232,240,0.85) 100%
    );
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
}
.hero-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 54px;
    font-weight: 300;
    color: #1a2a35;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    line-height: 1;
    margin: 0;
    text-shadow: 0 1px 12px rgba(255,255,255,0.9);
}
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 400;
    color: #3a5a6e;
    letter-spacing: 0.4em;
    text-transform: uppercase;
    margin: 0;
}

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #b8d0de !important;
    gap: 0 !important;
}
[data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    color: #7a9aaa !important;
    padding: 12px 28px !important;
    background: transparent !important;
    border: none !important;
    text-transform: uppercase !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #4a8fa8 !important;
    border-bottom: 2px solid #4a8fa8 !important;
}
[data-baseweb="tab-highlight"] { display: none !important; }
[data-baseweb="tab-border"]    { display: none !important; }

/* ── Metric boxes ── */
.mbox {
    background: #ffffff;
    border: 1px solid #b8d0de;
    border-radius: 14px;
    padding: 18px 12px;
    text-align: center;
    transition: border-color .25s, transform .25s;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.mbox:hover { border-color: #4a8fa866; transform: translateY(-2px); }
.msub {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: #7a9aaa;
    margin-top: 5px;
    letter-spacing: 0.04em;
}
.mprog-wrap {
    background: #dde8f0;
    border-radius: 4px;
    height: 5px;
    margin-top: 10px;
    overflow: hidden;
}
.mlabel {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 500;
    color: #7a9aaa;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.mvalue {
    font-family: 'Cormorant Garamond', serif;
    font-size: 32px;
    font-weight: 300;
    color: #4a8fa8;
    line-height: 1;
}

/* ── Section title ── */
.section-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 22px;
    font-weight: 300;
    color: #2c2010;
    letter-spacing: 0.08em;
    margin: 1.5rem 0 1rem;
    padding-bottom: 8px;
    border-bottom: 1px solid #b8d0de;
}

/* ── Cards ── */
.card {
    border: 1px solid #b8d0de;
    border-radius: 16px;
    overflow: hidden;
    background: #ffffff;
    margin-bottom: 20px;
    transition: border-color .3s, box-shadow .3s, transform .3s;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.card:hover {
    border-color: #4a8fa866;
    box-shadow: 0 8px 32px rgba(160,120,40,0.12);
    transform: translateY(-3px);
}
.card-img {
    width: 100%;
    aspect-ratio: 4/3;
    object-fit: cover;
    display: block;
    background: #f0ece6;
}
.card-img-placeholder {
    width: 100%;
    aspect-ratio: 4/3;
    background: linear-gradient(135deg, #ede8e0 0%, #eef3f7 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #c8bfb0;
    font-size: 42px;
}
.card-body { padding: 16px; }
.card-casa {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    font-weight: 500;
    color: #b0a898;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.card-artista {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 700;
    color: #1a2a35;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 4px;
    line-height: 1.3;
}
.card-titulo {
    font-family: 'Cormorant Garamond', serif;
    font-size: 15px;
    font-style: italic;
    font-weight: 400;
    color: #3a5a6e;
    text-transform: lowercase;
    margin-bottom: 8px;
    padding-top: 4px;
    border-top: 1px solid #dde8f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.card-meta {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    color: #7a9aaa;
    margin-bottom: 14px;
    letter-spacing: 0.05em;
}
.prices {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
}
.price-box {
    flex: 1;
    background: #faf8f5;
    border: 1px solid #e8e0d4;
    border-radius: 10px;
    padding: 10px 6px;
    text-align: center;
}
.price-label {
    font-family: 'Inter', sans-serif;
    font-size: 8px;
    font-weight: 500;
    color: #7a9aaa;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.price-val-base  { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #1a6fa8; }
.price-val-lance { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #1d7a4a; }
.price-val-est   { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #4a8fa8; }
.price-val-aval  { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #6b4bbf; }
.price-val-aval-vazio { font-family: 'Inter', sans-serif; font-size: 11px; color: #c0b8b0; }
.card-data-leilao {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 600;
    color: #4a8fa8;
    background: rgba(160,120,40,0.08);
    border: 1px solid rgba(160,120,40,0.22);
    border-radius: 6px;
    padding: 3px 8px;
    margin-bottom: 6px;
    display: inline-block;
    letter-spacing: 0.04em;
}
.rent-badge {
    display: inline-block;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 8px;
    margin-bottom: 8px;
    letter-spacing: 0.03em;
}
.rent-alto  { background: #e8f5ee; color: #1d7a4a; border: 1px solid #b0d8bf; }
.rent-medio { background: #fdf5e0; color: #9a7010; border: 1px solid #e0c870; }
.rent-baixo { background: #fde8e8; color: #a82020; border: 1px solid #e0b0b0; }
.rent-none  { background: #eef3f7; color: #b0a898; border: 1px solid #b8d0de; font-size: 11px; font-weight: 400; }
.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 4px;
}
.card-date {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    color: #c0b8b0;
    letter-spacing: 0.08em;
}
.badge {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    font-weight: 500;
    padding: 3px 9px;
    border-radius: 20px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.badge-lance   { background: #e8f5ee; color: #1d7a4a; border: 1px solid #b0d8bf; }
.badge-vendida { background: #e8f0fb; color: #1a5fa0; border: 1px solid #a8c8e8; }
.badge-semlan  { background: #eef3f7; color: #c0b8b0; border: 1px solid #b8d0de; }
.badge-ass     { background: rgba(160,120,40,0.10); color: #4a8fa8; border: 1px solid rgba(160,120,40,0.3); margin-left: 5px; }
.badge-nass    { background: #fde8e8; color: #a82020; border: 1px solid #e0b0b0; margin-left: 5px; }
.badge-mono    { background: #f0ebfb; color: #6b4bbf; border: 1px solid #c8b8e8; margin-left: 5px; }
.card-link { margin-top: 10px; }
.card-link a {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 500;
    color: #1a6fa8 !important;
    text-decoration: none;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.card-link a:hover { color: #4a8fa8 !important; }

/* ── Divider ── */
hr { border: none; border-top: 1px solid #b8d0de; margin: 1.5rem 0; }

/* ── Inputs e selects ── */
[data-baseweb="input"] input,
[data-baseweb="select"] div {
    background: #ffffff !important;
    border-color: #b8d0de !important;
    color: #1a2a35 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
label[data-testid="stWidgetLabel"] p {
    font-family: 'Inter', sans-serif !important;
    font-size: 10px !important;
    font-weight: 500 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: #7a9aaa !important;
}
[data-testid="stCheckbox"] label p {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    color: #3a5a6e !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #b8d0de !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary {
    color: #3a5a6e !important;
}
/* ── Tabs (duplicado para garantir) ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #b8d0de !important;
}
[data-baseweb="tab"] {
    color: #7a9aaa !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #4a8fa8 !important;
    border-bottom: 2px solid #4a8fa8 !important;
}
/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Carrega dados ───────────────────────────────────────────────────────────────
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["artista", "titulo", "tecnica", "dimensoes", "ano", "casa", "assinatura", "foto_url"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    for col in ["lance_base", "maior_lance", "estimativa_min", "estimativa_max"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "num_lances" not in df.columns:
        df["num_lances"] = 0
    df["num_lances"] = pd.to_numeric(df["num_lances"], errors="coerce").fillna(0).astype(int)
    for col in ["data_leilao", "data_coleta", "url_detalhe", "status"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    return df


def _tab_parse_data(data_str):
    """Extrai data normalizada (d/m/yyyy) de string Tableau como 'TERÇA FEIRA (24/03/2026) a partir...'"""
    import re as _r
    m = _r.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', data_str or "")
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{d}/{mo}/{y}"
    return ""


def _tableau_to_standard(rows: list) -> pd.DataFrame:
    """Normaliza campos do Tableau para o padrão da plataforma."""
    out = []
    for r in rows:
        out.append({
            "artista":      r.get("artista", ""),
            "titulo":       r.get("titulo", ""),
            "tecnica":      r.get("tecnica", ""),
            "dimensoes":    r.get("medidas", ""),
            "ano":          r.get("data_obra", ""),
            "assinatura":   r.get("assinado", ""),
            "lance_base":   r.get("valor_base", 0) or 0,
            "maior_lance":  r.get("lance_atual", 0) or 0,
            "num_lances":   0,
            "status":       r.get("tipo_lance", "Em leilão"),
            "data_leilao":  _tab_parse_data(r.get("data_leilao", "")),
            "casa":         "Tableau Arte & Leilões",
            "data_coleta":  r.get("coletado_em", ""),
            "url_detalhe":  r.get("url_lote", ""),
            "foto_url":     r.get("img_grande", "") or r.get("img_thumb", ""),
            "em_leilao":    True,
        })
    return pd.DataFrame(out)


@st.cache_data(ttl=30)
def _cobertura_precos(artistas_tuple):
    """% de artistas em leilão que aparecem no Histórico de Preços.
    Usa as mesmas fontes que load_historico() — qualquer registro basta,
    independente de ter preço de arrematação."""
    import unicodedata as _ud, re as _re

    def _norm(s):
        s = _re.sub(r'\(.*?\)', '', s or '').strip()
        nfkd = _ud.normalize('NFKD', s.upper())
        s = ''.join(c for c in nfkd if not _ud.combining(c))
        return _re.sub(r'\s+', ' ', _re.sub(r'[^A-Z\s]', '', s)).strip()

    # Conjunto de todos os artistas que aparecem no histórico (sem filtro de preço)
    art_historico = set()

    try:
        # BDA + CDA — qualquer registro com artista válido
        for arq in [BDA_FILE, CDA_FILE]:
            if not os.path.exists(arq):
                continue
            with open(arq, "r", encoding="utf-8") as f:
                d = json.load(f)
            for v in d.values():
                if isinstance(v, dict):
                    n = _norm(v.get("artista", ""))
                    if n:
                        art_historico.add(n)

        # LeiloesBR finalizados
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            for v in d.values():
                if isinstance(v, dict) and not v.get("_ignorado") and v.get("em_leilao") is False:
                    n = _norm(v.get("artista", ""))
                    if n:
                        art_historico.add(n)

        # ArremateArte finalizados
        if os.path.exists(ARR_FILE):
            with open(ARR_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            for k, v in d.items():
                if not k.startswith("__meta") and isinstance(v, dict) and not v.get("em_leilao", True):
                    n = _norm(v.get("artista", ""))
                    if n:
                        art_historico.add(n)

        # Tableau passados
        if os.path.exists(TAB_FILE):
            from datetime import date as _date_cls
            _today = _date_cls.today()
            with open(TAB_FILE, "r", encoding="utf-8") as f:
                raw_tab = json.load(f)
            for r in raw_tab:
                m = _re.search(r'\((\d{1,2}/\d{2}/\d{4})\)', r.get("data_leilao", ""))
                if m:
                    try:
                        pts = m.group(1).split('/')
                        if _date_cls(int(pts[2]), int(pts[1]), int(pts[0])) < _today:
                            n = _norm(r.get("artista", ""))
                            if n:
                                art_historico.add(n)
                    except Exception:
                        pass
    except Exception:
        pass

    total   = len(artistas_tuple)
    com_ref = sum(1 for a in artistas_tuple if _norm(a) in art_historico)
    sem_ref = total - com_ref
    pct     = round(100 * com_ref / total) if total > 0 else 0
    sem_lista = sorted(
        [a for a in artistas_tuple if _norm(a) not in art_historico],
        key=lambda s: s.lower(),
    )
    return com_ref, sem_ref, total, pct, sem_lista


def _data_leilao_passou(data_str):
    """Retorna True se a data do leilão já passou (ontem ou antes)."""
    import datetime
    if not data_str:
        return False
    try:
        partes = str(data_str).split("/")
        if len(partes) == 3:
            dt = datetime.date(int(partes[2]), int(partes[1]), int(partes[0]))
            return dt < datetime.date.today()
    except Exception:
        pass
    return False


def _sb_fetch_all(table, filters=None, columns="*", page_size=1000):
    """Busca todos os registros de uma tabela Supabase com paginação."""
    rows = []
    offset = 0
    while True:
        q = _SB.table(table).select(columns)
        if filters:
            for col, val in filters.items():
                if val is True:
                    q = q.eq(col, True)
                elif val is False:
                    q = q.eq(col, False)
                else:
                    q = q.eq(col, val)
        result = q.range(offset, offset + page_size - 1).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


@st.cache_data(ttl=300)
def load_leiloes():
    """Lotes ativos — todas as fontes. Exclui lotes com data já passada."""
    if _USE_SUPABASE:
        rows = _sb_fetch_all("lotes", filters={"em_leilao": True, "ignorado": False})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if "data_leilao" in df.columns:
            df = df[~df["data_leilao"].apply(_data_leilao_passou)]
        # Recria foto_url para leiloesbr sem foto (chave tem 4 partes separadas por |)
        if "foto_url" in df.columns and "chave" in df.columns:
            mask = (df["fonte"] == "leiloesbr") & (df["foto_url"].isna() | (df["foto_url"] == ""))
            def _fix_foto(chave):
                parts = chave.replace("leiloesbr|", "", 1).split("|")
                if len(parts) == 4:
                    return f"https://d1o6h00a1h5k7q.cloudfront.net/imagens/img_g/{parts[2]}/{parts[3]}.jpg"
                return ""
            df.loc[mask, "foto_url"] = df.loc[mask, "chave"].apply(_fix_foto)
        return _normalize_df(df)

    # ── Fallback: leitura local ──────────────────────────────────────────────
    frames = []
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = []
        for k, v in raw.items():
            if not isinstance(v, dict): continue
            if v.get("_ignorado"): continue
            if not v.get("em_leilao", True): continue
            if _data_leilao_passou(v.get("data_leilao", "")): continue
            if not v.get("foto_url"):
                parts = k.split("|")
                if len(parts) == 4:
                    v = dict(v)
                    v["foto_url"] = (
                        f"https://d1o6h00a1h5k7q.cloudfront.net"
                        f"/imagens/img_g/{parts[2]}/{parts[3]}.jpg"
                    )
            rows.append(v)
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(ARR_FILE):
        with open(ARR_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = [v for k, v in raw.items()
                if not k.startswith("__meta") and isinstance(v, dict)
                and v.get("em_leilao", False)
                and not _data_leilao_passou(v.get("data_leilao", ""))]
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(TAB_FILE):
        with open(TAB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list) and raw:
            df_tab = _tableau_to_standard(raw)
            if not df_tab.empty:
                df_tab = df_tab[~df_tab["data_leilao"].apply(_data_leilao_passou)]
                if not df_tab.empty:
                    frames.append(df_tab)
    if not frames:
        return pd.DataFrame()
    return _normalize_df(pd.concat(frames, ignore_index=True))


@st.cache_data(ttl=300)
def load_historico():
    """Histórico de preços — todas as fontes finalizadas."""
    if _USE_SUPABASE:
        rows = _sb_fetch_all("lotes", filters={"em_leilao": False})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df[df["artista"].notna() & (df["artista"] != "")]
        return _normalize_df(df)

    # ── Fallback: leitura local ──────────────────────────────────────────────
    frames = []
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = [v for v in raw.values()
                if isinstance(v, dict) and not v.get("_ignorado")
                and v.get("em_leilao") is False]
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(BDA_FILE):
        with open(BDA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = [v for k, v in raw.items() if k != "__meta__" and isinstance(v, dict) and v.get("artista")]
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(CDA_FILE):
        with open(CDA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = [v for k, v in raw.items() if k != "__meta__" and isinstance(v, dict) and v.get("artista")]
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(ARR_FILE):
        with open(ARR_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = [v for k, v in raw.items()
                if not k.startswith("__meta") and isinstance(v, dict)
                and v.get("artista") and not v.get("em_leilao", True)]
        if rows:
            frames.append(pd.DataFrame(rows))
    if os.path.exists(TAB_FILE):
        from datetime import date as _date_cls
        _today = _date_cls.today()
        with open(TAB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        tab_hist = []
        for r in raw:
            if not r.get("artista"): continue
            d_str = r.get("data_leilao","")
            m = _re.search(r'\((\d{1,2}/\d{2}/\d{4})\)', d_str)
            if m:
                try:
                    parts = m.group(1).split('/')
                    dt = _date_cls(int(parts[2]), int(parts[1]), int(parts[0]))
                    if dt < _today:
                        tab_hist.append({
                            "artista":     r.get("artista",""),
                            "titulo":      r.get("titulo",""),
                            "tecnica":     r.get("tecnica",""),
                            "maior_lance": r.get("lance_atual", 0) or 0,
                            "lance_base":  r.get("valor_base", 0) or 0,
                            "data_leilao": dt.strftime("%d/%m/%Y"),
                            "casa":        "Tableau Arte & Leilões",
                            "em_leilao":   False,
                        })
                except Exception:
                    pass
        if tab_hist:
            frames.append(pd.DataFrame(tab_hist))
    if not frames:
        return pd.DataFrame()
    return _normalize_df(pd.concat(frames, ignore_index=True))


@st.cache_data(ttl=600)
def load_media_hist():
    """Média histórica por artista.
    Retorna dict norm_name → {"lance": média_lances, "base": média_bases}
    Campos ausentes ficam em 0.
    """
    lances = {}   # art_norm → [valores]
    bases  = {}

    def _add(art, lance, base):
        if not art: return
        if lance > 0: lances.setdefault(art, []).append(lance)
        if base  > 0: bases.setdefault(art,  []).append(base)

    if _USE_SUPABASE:
        rows = _sb_fetch_all("lotes", filters={"em_leilao": False},
                             columns="artista,maior_lance,lance_base")
        for v in rows:
            art = _norm_art(v.get("artista", ""))
            try: ml = float(v.get("maior_lance") or 0)
            except Exception: ml = 0
            try: mb = float(v.get("lance_base") or 0)
            except Exception: mb = 0
            _add(art, ml, mb)
        # Histórico Levy + Conrad (lance_base não existe nessa tabela)
        try:
            hcf_rows = _sb_fetch_all("historico_casas", columns="artista,maior_lance")
            for v in hcf_rows:
                art = _norm_art(v.get("artista", ""))
                try: ml = float(v.get("maior_lance") or 0)
                except Exception: ml = 0
                _add(art, ml, 0)
        except Exception:
            pass
        arts = set(lances) | set(bases)
        return {
            art: {
                "lance": round(sum(lances[art]) / len(lances[art])) if art in lances else 0,
                "base":  round(sum(bases[art])  / len(bases[art]))  if art in bases  else 0,
            }
            for art in arts
        }

    # ── Fallback: leitura local ──────────────────────────────────────────────
    for arq in [BDA_FILE, CDA_FILE]:
        if not os.path.exists(arq): continue
        with open(arq, "r", encoding="utf-8") as f:
            d = json.load(f)
        for v in d.values():
            if not isinstance(v, dict): continue
            art = _norm_art(v.get("artista", ""))
            try: ml = float(v.get("maior_lance") or v.get("lance_atual") or 0)
            except Exception: ml = 0
            try: mb = float(v.get("lance_base") or 0)
            except Exception: mb = 0
            _add(art, ml, mb)
    for arq in [DB_FILE, ARR_FILE]:
        if not os.path.exists(arq): continue
        with open(arq, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if not isinstance(v, dict) or v.get("em_leilao") is not False: continue
            art = _norm_art(v.get("artista", ""))
            try: ml = float(v.get("maior_lance") or 0)
            except Exception: ml = 0
            try: mb = float(v.get("lance_base") or 0)
            except Exception: mb = 0
            _add(art, ml, mb)
    if os.path.exists(HCF_FILE):
        with open(HCF_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        for v in d.get("lotes", []):
            if not isinstance(v, dict): continue
            art = _norm_art(v.get("artista", ""))
            try: ml = float(v.get("maior_lance") or 0)
            except Exception: ml = 0
            try: mb = float(v.get("lance_base") or 0)
            except Exception: mb = 0
            _add(art, ml, mb)
    arts = set(lances) | set(bases)
    return {
        art: {
            "lance": round(sum(lances[art]) / len(lances[art])) if art in lances else 0,
            "base":  round(sum(bases[art])  / len(bases[art]))  if art in bases  else 0,
        }
        for art in arts
    }


def fmt_brl(v):
    if v and v > 0:
        return f"R$ {v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "—"


def fmt_m2(v):
    """Formata valor por m² em BRL."""
    if v and v > 0:
        return f"R$ {v:,.0f}/m²".replace(",", "X").replace(".", ",").replace("X", ".")
    return ""


# ── Dimensões → área ─────────────────────────────────────────────────────────────
_RE_DIMS = _re.compile(
    r'(\d+[,.]?\d*)\s*(?:cm)?\s*[xX×]\s*(\d+[,.]?\d*)\s*(cm|m)?',
    _re.IGNORECASE,
)


def _parse_area_cm2(dims: str) -> float | None:
    """Extrai área em cm² de string de dimensões (ex: '100 x 80 cm' → 8000.0).
    Retorna None se não conseguir parsear."""
    if not dims:
        return None
    m = _RE_DIMS.search(str(dims))
    if not m:
        return None
    try:
        v1 = float(m.group(1).replace(",", "."))
        v2 = float(m.group(2).replace(",", "."))
        unit = (m.group(3) or "cm").lower()
        if unit == "m":
            v1 *= 100
            v2 *= 100
        area = v1 * v2
        if area <= 0 or area > 2_000_000:  # sanity check (max ~14x14m)
            return None
        return area
    except Exception:
        return None


def _r_por_m2(preco: float, dims: str) -> float | None:
    """Calcula preço por m² dado preço e string de dimensões. Retorna None se não parsear."""
    area = _parse_area_cm2(dims)
    if not area or area <= 0:
        return None
    return preco / area * 10_000  # cm² → m²


# ── Helpers de artista ──────────────────────────────────────────────────────────
def _to_title(s: str) -> str:
    """Converte nome para title case preservando partículas minúsculas."""
    _particles = {"de", "da", "do", "dos", "das", "e", "di", "del", "van", "von"}
    words = s.strip().split()
    return " ".join(
        w.capitalize() if w.lower() not in _particles or i == 0 else w.lower()
        for i, w in enumerate(words)
    )


def _build_artistas_opcoes(df):
    """Constrói lista de artistas únicos agrupando variantes pelo nome normalizado.
    Retorna lista de tuplas (norm, nome_principal, label_display) ordenada A-Z."""
    from collections import Counter
    grupos = {}
    for art in df["artista"].dropna():
        art = str(art).strip()
        if not art:
            continue
        n = _norm_art(art)
        if not n:
            continue
        grupos.setdefault(n, Counter())[art] += 1

    result = []
    for n, cnt in grupos.items():
        # Prefere versão title case; fallback para mais frequente
        principal_raw = cnt.most_common(1)[0][0]
        # Tenta encontrar uma variante já em title case
        title_variante = next(
            (v for v in cnt if v == _to_title(v) and v[0].isupper()), None
        )
        principal = title_variante or _to_title(principal_raw)
        total = sum(cnt.values())
        label = f"{principal}  [{total}]"
        result.append((n, principal, label))

    result.sort(key=lambda x: x[1])
    return result


# ── Filtros comuns ──────────────────────────────────────────────────────────────
def render_filtros(df_all, prefix="", campo_preco="lance_base"):
    col_a, col_b, col_c = st.columns([3, 2, 2])
    with col_a:
        _opcoes = _build_artistas_opcoes(df_all)
        _labels     = [o[2] for o in _opcoes]   # "Nome Artista  [N]"
        _principals = [o[1] for o in _opcoes]
        _norms      = [o[0] for o in _opcoes]
        sel_label = st.selectbox(
            "Artista",
            options=_labels,
            index=None,
            placeholder="Digite ou selecione um artista…",
            key=f"{prefix}_artista",
        )
        if sel_label is None:
            busca_artista = ""
            busca_artista_norm = ""
        else:
            _i = _labels.index(sel_label)
            busca_artista = _principals[_i]
            busca_artista_norm = _norms[_i]
    with col_b:
        lista_casas = sorted(df_all["casa"].replace("", pd.NA).dropna().unique().tolist())
        casa_sel = st.selectbox("Fonte", ["Todas"] + lista_casas, key=f"{prefix}_casa")
    with col_c:
        busca_titulo = st.text_input("Título / Técnica", placeholder="ex: marinha, óleo…", key=f"{prefix}_titulo")

    col_d, col_e, col_f = st.columns(3)
    with col_d:
        filtro_ass = st.selectbox("Assinatura", ["Todas", "Assinado", "Não assinado", "Monogramado", "Sem info"], key=f"{prefix}_ass")
    with col_e:
        apenas_foto = st.checkbox("Só com foto", key=f"{prefix}_foto")
    with col_f:
        apenas_base = st.checkbox("Só com valor", key=f"{prefix}_base")

    # Faixa de preço
    precos = df_all[campo_preco].dropna()
    precos_validos = precos[precos > 0]
    preco_min_slider = preco_max_slider = (0, 0)
    if not precos_validos.empty:
        vmin = int(precos_validos.min())
        vmax = int(precos_validos.max())
        if vmin < vmax:
            preco_min_slider, preco_max_slider = st.slider(
                "Faixa de valor (R$)",
                min_value=vmin, max_value=vmax,
                value=(vmin, vmax),
                format="R$ %d",
                key=f"{prefix}_preco_range"
            )
        else:
            preco_min_slider, preco_max_slider = vmin, vmax

    return busca_artista, busca_artista_norm, busca_titulo, casa_sel, filtro_ass, apenas_foto, apenas_base, (preco_min_slider, preco_max_slider)


def aplicar_filtros(df, busca_artista, busca_artista_norm, busca_titulo, casa_sel, filtro_ass, apenas_foto, apenas_base, preco_range=None, campo_preco="lance_base"):
    if busca_artista_norm:
        # Busca parcial normalizada: "picasso" acha "Pablo Picasso", ignora acentos/case
        df = df[df["artista"].apply(lambda x: busca_artista_norm in _norm_art(str(x)))]
    if busca_titulo.strip():
        df = df[
            df["titulo"].str.contains(busca_titulo.strip(), case=False, na=False)
            | df["tecnica"].str.contains(busca_titulo.strip(), case=False, na=False)
        ]
    if casa_sel != "Todas":
        df = df[df["casa"] == casa_sel]
    if filtro_ass == "Sem info":
        df = df[df["assinatura"] == ""]
    elif filtro_ass != "Todas":
        df = df[df["assinatura"] == filtro_ass]
    if apenas_foto:
        df = df[df["foto_url"] != ""]
    if apenas_base:
        df = df[df[campo_preco] > 0]
    if preco_range and preco_range[0] != preco_range[1]:
        pmin, pmax = preco_range
        mask = (df[campo_preco] == 0) | ((df[campo_preco] >= pmin) & (df[campo_preco] <= pmax))
        df = df[mask]
    return df


def render_grafico_artista(df_hist, artista: str):
    """Gráfico de evolução de preços do artista ao longo do tempo."""
    _norm_sel = _norm_art(artista)
    df_a = df_hist[
        (df_hist["artista"].apply(lambda x: _norm_art(str(x))) == _norm_sel) &
        (df_hist["maior_lance"] > 0)
    ].copy()

    if df_a.empty:
        return

    # Tenta parsear data_leilao
    df_a["_data"] = pd.to_datetime(df_a["data_leilao"], dayfirst=True, errors="coerce")
    df_a = df_a.dropna(subset=["_data"]).sort_values("_data")

    if len(df_a) < 2:
        return

    st.markdown(f"#### 📈 Evolução de preços — {artista.title()}")

    col_g, col_s = st.columns([3, 1])
    with col_g:
        fig = px.scatter(
            df_a,
            x="_data", y="maior_lance",
            hover_data={"titulo": True, "casa": True, "maior_lance": ":,.0f", "_data": False},
            labels={"_data": "Data", "maior_lance": "Lance (R$)", "titulo": "Título"},
            color_discrete_sequence=["#e0a84b"],
        )
        fig.add_traces(
            px.line(df_a, x="_data", y="maior_lance", color_discrete_sequence=["#e0a84b33"]).data
        )
        fig.update_layout(
            plot_bgcolor="#0e0e1a", paper_bgcolor="#0e0e1a",
            font_color="#ccc",
            xaxis=dict(gridcolor="#222"), yaxis=dict(gridcolor="#222"),
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False,
        )
        fig.update_yaxes(tickprefix="R$ ", tickformat=",")
        st.plotly_chart(fig, use_container_width=True)

    with col_s:
        lances = df_a["maior_lance"]
        st.metric("Obras arrematadas", len(df_a))
        st.metric("Mediana", fmt_brl(lances.median()))
        st.metric("Máximo", fmt_brl(lances.max()))
        st.metric("Mínimo", fmt_brl(lances.min()))
        delta = lances.iloc[-1] - lances.iloc[0] if len(lances) > 1 else 0
        pct = (delta / lances.iloc[0] * 100) if lances.iloc[0] > 0 else 0
        st.metric("1º → Último", fmt_brl(lances.iloc[-1]),
                  delta=f"{pct:+.0f}%" if pct else None)


# ── Cards ───────────────────────────────────────────────────────────────────────
_ASS_MAP = {
    "Assinado":     ("✍️", "badge-ass"),
    "Não assinado": ("✗",  "badge-nass"),
    "Monogramado":  ("M",  "badge-mono"),
    "Rubricado":    ("R",  "badge-mono"),
}

NCOLS    = 4
PER_PAGE = 20   # cards por página (5 linhas × 4 colunas)


def render_cards_leilao(df):
    media_hist = load_media_hist()
    rows = [df.iloc[i:i+NCOLS] for i in range(0, len(df), NCOLS)]
    for row_df in rows:
        cols = st.columns(NCOLS)
        for col, (_, item) in zip(cols, row_df.iterrows()):
            artista  = item["artista"]   or "Desconhecido"
            titulo   = item["titulo"]    or "Sem título"
            tecnica  = item["tecnica"]   or ""
            dims     = item["dimensoes"] or ""
            ano      = item["ano"]       or ""
            foto_url = item["foto_url"]  or ""
            base     = fmt_brl(item["lance_base"])
            lance    = fmt_brl(item["maior_lance"])
            nlances  = item["num_lances"]
            casa     = item["casa"]      or ""
            data     = item["data_leilao"] or item["data_coleta"] or ""
            url      = item["url_detalhe"] or ""
            assinatura = item["assinatura"] or ""
            _art_norm   = _norm_art(artista)
            _mh_entry   = media_hist.get(_art_norm, {})
            _aval_lance = _mh_entry.get("lance", 0)
            _aval_base  = _mh_entry.get("base", 0)
            _base_val   = item["lance_base"]

            if _aval_lance > 0 and _aval_base > 0:
                aval_disp = (f'<span class="price-val-aval">{fmt_brl(_aval_lance)}</span>'
                             f'<div style="font-size:9px;color:#7a9aaa;margin-top:2px">'
                             f'base méd. {fmt_brl(_aval_base)}</div>')
            elif _aval_lance > 0:
                aval_disp = f'<span class="price-val-aval">{fmt_brl(_aval_lance)}</span>'
            elif _aval_base > 0:
                aval_disp = (f'<span class="price-val-aval-vazio">sem lances</span>'
                             f'<div style="font-size:9px;color:#7a9aaa;margin-top:2px">'
                             f'base méd. {fmt_brl(_aval_base)}</div>')
            else:
                aval_disp = '<span class="price-val-aval-vazio">sem histórico</span>'

            # Badge de rentabilidade (usa média de lances como referência)
            _ref = _aval_lance or _aval_base
            if _ref > 0 and _base_val > 0:
                _rent = (_ref / _base_val - 1) * 100
                if _rent >= 100:
                    _rent_cls = "rent-alto"
                    _rent_lbl = f"▲ {_rent:,.0f}% potencial"
                elif _rent >= 20:
                    _rent_cls = "rent-medio"
                    _rent_lbl = f"▲ {_rent:,.0f}% potencial"
                elif _rent >= 0:
                    _rent_cls = "rent-baixo"
                    _rent_lbl = f"▲ {_rent:,.0f}% potencial"
                else:
                    _rent_cls = "rent-baixo"
                    _rent_lbl = f"▼ base acima do histórico"
            else:
                _rent_cls = "rent-none"
                _rent_lbl = "sem referência histórica"
            rent_html = f'<div class="rent-badge {_rent_cls}">{_rent_lbl}</div>'

            badge_lance = (
                f'<span class="badge badge-lance">🔨 {nlances} lance{"s" if nlances != 1 else ""}</span>'
                if nlances > 0 else
                '<span class="badge badge-semlan">Sem lances</span>'
            )
            badge_ass = ""
            if assinatura in _ASS_MAP:
                ic, cls = _ASS_MAP[assinatura]
                badge_ass = f'<span class="badge {cls}">{ic} {assinatura}</span>'

            meta_str = " · ".join(x for x in [tecnica, dims, ano] if x) or "&nbsp;"
            img_html = (
                f'<img class="card-img" src="{foto_url}" loading="lazy" referrerpolicy="no-referrer" '
                f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
                f'<div class="card-img-placeholder" style="display:none">🖼️</div>'
                if foto_url else '<div class="card-img-placeholder">🖼️</div>'
            )
            link_html = f'<a href="{url}" target="_blank">Ver lote ↗</a>' if url else ""

            data_html = (
                f'<div class="card-data-leilao">📅 {data}</div>'
                if data else ""
            )

            with col:
                st.markdown(f"""
<div class="card">
  {img_html}
  <div class="card-body">
    <div class="card-casa">{casa}</div>
    {data_html}
    {rent_html}
    <div class="card-artista">{artista}</div>
    <div class="card-titulo" title="{titulo}">{titulo}</div>
    <div class="card-meta">{meta_str}</div>
    <div class="prices">
      <div class="price-box">
        <div class="price-label">Valor Base</div>
        <div class="price-val-base">{base}</div>
      </div>
      <div class="price-box">
        <div class="price-label">Maior Lance</div>
        <div class="price-val-lance">{lance}</div>
      </div>
      <div class="price-box">
        <div class="price-label">Histórico</div>
        {aval_disp}
      </div>
    </div>
    <div class="card-footer">
      <div>{badge_lance}{badge_ass}</div>
    </div>
    <div class="card-link">{link_html}</div>
  </div>
</div>
""", unsafe_allow_html=True)
                _fav_url = item["url_detalhe"] or item.get("foto_url", "")
                _is_fav  = _fav_url in get_favoritos()
                _fav_lbl = "★ Salvo" if _is_fav else "☆ Favoritar"
                _fav_css = "color:#c9a96e;" if _is_fav else "color:#555;"
                if st.button(_fav_lbl, key=f"fav_{hash(_fav_url)}",
                             use_container_width=True,
                             help="Salvar / remover dos favoritos"):
                    toggle_favorito(_fav_url)
                    st.rerun()


def render_cards_historico(df):
    media_hist = load_media_hist()
    rows = [df.iloc[i:i+NCOLS] for i in range(0, len(df), NCOLS)]
    for row_df in rows:
        cols = st.columns(NCOLS)
        for col, (_, item) in zip(cols, row_df.iterrows()):
            artista    = item["artista"]   or "Desconhecido"
            titulo     = item["titulo"]    or "Sem título"
            tecnica    = item["tecnica"]   or ""
            dims       = item["dimensoes"] or ""
            ano        = item["ano"]       or ""
            foto_url   = item["foto_url"]  or ""
            est_min    = item["estimativa_min"]
            est_max    = item["estimativa_max"]
            lance      = item["maior_lance"]
            casa       = item["casa"]      or ""
            data       = item["data_leilao"] or item["data_coleta"] or ""
            url        = item["url_detalhe"] or ""
            assinatura = item["assinatura"] or ""
            status     = item.get("status", "") or ""
            _art_norm   = _norm_art(artista)
            _mh_entry   = media_hist.get(_art_norm, {})
            _aval_lance = _mh_entry.get("lance", 0)
            _aval_base  = _mh_entry.get("base", 0)

            if _aval_lance > 0 and _aval_base > 0:
                aval_disp = (f'<span class="price-val-aval">{fmt_brl(_aval_lance)}</span>'
                             f'<div style="font-size:9px;color:#7a9aaa;margin-top:2px">'
                             f'base méd. {fmt_brl(_aval_base)}</div>')
            elif _aval_lance > 0:
                aval_disp = f'<span class="price-val-aval">{fmt_brl(_aval_lance)}</span>'
            elif _aval_base > 0:
                aval_disp = (f'<span class="price-val-aval-vazio">sem lances</span>'
                             f'<div style="font-size:9px;color:#7a9aaa;margin-top:2px">'
                             f'base méd. {fmt_brl(_aval_base)}</div>')
            else:
                aval_disp = '<span class="price-val-aval-vazio">sem histórico</span>'

            # % do arremate em relação à média de lances histórica
            _ref = _aval_lance or _aval_base
            if _ref > 0 and lance > 0:
                _pct = round(lance / _ref * 100)
                if _pct <= 80:
                    _pct_color, _pct_bg = "#1d7a4a", "#e8f5ee"
                elif _pct <= 110:
                    _pct_color, _pct_bg = "#9a7010", "#fdf5e0"
                else:
                    _pct_color, _pct_bg = "#a82020", "#fde8e8"
                _pct_str = (
                    f'<div style="margin-top:4px;padding:3px 8px;border-radius:6px;'
                    f'background:{_pct_bg};display:inline-block">'
                    f'<span style="font-size:12px;color:{_pct_color};font-weight:700">'
                    f'{_pct}% da média hist.</span></div>'
                )
            else:
                _pct_str = ""

            # Faixa de estimativa
            if est_min > 0 and est_max > 0:
                est_str = f"{fmt_brl(est_min)} – {fmt_brl(est_max)}"
            elif est_min > 0:
                est_str = fmt_brl(est_min)
            else:
                est_str = "—"

            lance_str = fmt_brl(lance)

            badge_status = ""
            if lance > 0:
                badge_status = '<span class="badge badge-vendida">✔ Arrematado</span>'
            elif status:
                badge_status = f'<span class="badge badge-semlan">{status}</span>'

            badge_ass = ""
            if assinatura in _ASS_MAP:
                ic, cls = _ASS_MAP[assinatura]
                badge_ass = f'<span class="badge {cls}">{ic} {assinatura}</span>'

            meta_str = " · ".join(x for x in [tecnica, dims, ano] if x) or "&nbsp;"
            img_html = (
                f'<img class="card-img" src="{foto_url}" loading="lazy" referrerpolicy="no-referrer" '
                f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
                f'<div class="card-img-placeholder" style="display:none">🖼️</div>'
                if foto_url else '<div class="card-img-placeholder">🖼️</div>'
            )
            link_html = f'<a href="{url}" target="_blank">Ver obra ↗</a>' if url else ""

            with col:
                st.markdown(f"""
<div class="card">
  {img_html}
  <div class="card-body">
    <div class="card-casa">{casa}</div>
    <div class="card-artista">{artista}</div>
    <div class="card-titulo" title="{titulo}">{titulo}</div>
    <div class="card-meta">{meta_str}</div>
    <div class="prices">
      <div class="price-box">
        <div class="price-label">Estimativa</div>
        <div class="price-val-est">{est_str}</div>
      </div>
      <div class="price-box">
        <div class="price-label">Último Lance</div>
        <div class="price-val-lance">{lance_str}</div>
        {_pct_str}
      </div>
      <div class="price-box">
        <div class="price-label">Histórico</div>
        {aval_disp}
      </div>
    </div>
    <div class="card-footer">
      <div>{badge_status}{badge_ass}</div>
      <span style="font-size:10px;color:#555">{data}</span>
    </div>
    <div class="card-link">{link_html}</div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_resumo_artista(df):
    resumo = (
        df[df["artista"] != ""]
        .groupby("artista")
        .agg(
            Obras=("artista", "count"),
            Base_Min=("lance_base",   lambda x: x[x > 0].min() if (x > 0).any() else None),
            Base_Max=("lance_base",   lambda x: x[x > 0].max() if (x > 0).any() else None),
            Lance_Max=("maior_lance", lambda x: x[x > 0].max() if (x > 0).any() else None),
        )
        .reset_index()
        .sort_values("Obras", ascending=False)
    )
    for c in ["Base_Min", "Base_Max", "Lance_Max"]:
        resumo[c] = resumo[c].apply(lambda v: fmt_brl(v) if pd.notna(v) and v else "—")
    resumo.columns = ["Artista", "Obras", "Menor Valor", "Maior Valor", "Maior Lance"]
    st.dataframe(resumo, use_container_width=True, hide_index=True)




def render_cards_por_artista(df):
    """Exibe cards agrupados por artista (seção por artista, cards dentro)."""
    media_hist = load_media_hist()
    df = df.copy()
    df["_art_sort"] = df["artista"].apply(lambda x: _norm_art(str(x)) or "zzz")
    df = df.sort_values(["_art_sort", "lance_base"], ascending=[True, False])

    grupos = df.groupby("_art_sort", sort=False)
    for art_norm, grupo in grupos:
        nome = grupo["artista"].iloc[0] or "Desconhecido"
        n = len(grupo)
        _mhe = media_hist.get(art_norm, {})
        _al, _ab = _mhe.get("lance", 0), _mhe.get("base", 0)
        aval_str = (f" · lances: {fmt_brl(_al)}" if _al else "") + (f" · base: {fmt_brl(_ab)}" if _ab else "")
        st.markdown(
            f'<div style="background:#f0ece6;border-left:3px solid #4a8fa8;'
            f'padding:8px 14px;margin:18px 0 6px;border-radius:0 6px 6px 0">'
            f'<span style="font-weight:700;font-size:15px;color:#1a2a35">{nome}</span>'
            f'<span style="color:#7a9aaa;font-size:12px;margin-left:10px">{n} lote{"s" if n>1 else ""}{aval_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        render_cards_leilao(grupo.drop(columns=["_art_sort"]))


def render_duplicatas(df):
    """Detecta e exibe lotes que aparecem em mais de uma casa (mesma obra, casas diferentes)."""
    if df.empty:
        return

    df = df.copy()
    df["_art_n"] = df["artista"].apply(lambda x: _norm_art(str(x)))
    df["_tit_n"] = df["titulo"].apply(
        lambda x: _re.sub(r'\s+', ' ', _re.sub(r'[^a-z0-9 ]', '', _norm_art(str(x)))).strip()
    )
    # Considera duplicata: mesmo artista E título normalizado com >= 6 chars
    df_valido = df[(df["_art_n"] != "") & (df["_tit_n"].str.len() >= 6)].copy()

    grupos = df_valido.groupby(["_art_n", "_tit_n"]).filter(lambda g: g["casa"].nunique() > 1)

    if grupos.empty:
        st.info("Nenhuma duplicata detectada no conjunto filtrado.")
        return

    n_obras = grupos.groupby(["_art_n", "_tit_n"]).ngroups
    st.markdown(f"**{n_obras}** obra(s) aparecem em mais de uma casa:")
    st.markdown("---")

    media_hist = load_media_hist()
    for (art_n, tit_n), grupo in grupos.groupby(["_art_n", "_tit_n"]):
        casas = ", ".join(grupo["casa"].unique())
        nome = grupo["artista"].iloc[0] or "Desconhecido"
        titulo = grupo["titulo"].iloc[0] or "Sem título"
        st.markdown(
            f'<div style="background:#1c1c30;border:1px solid #f59e0b44;border-radius:8px;padding:10px 14px;margin-bottom:10px">'
            f'<span style="color:#f59e0b;font-weight:700">⚠ Duplicata</span> · '
            f'<b>{nome}</b> — {titulo[:70]}<br>'
            f'<span style="color:#888;font-size:12px">Casas: {casas} · {len(grupo)} lotes</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        render_cards_leilao(grupo.drop(columns=["_art_n", "_tit_n"]))


# ── Garimpo Visual ──────────────────────────────────────────────────────────
_RE_DESCONHECIDO = _re.compile(
    r'\b(n[aã]o\s+identificad|desconhecid|an[oô]nim|atribu[ií]d|attr\b|'
    r'sem\s+autoria|incerto|s\.a\b|s/a\b|unknown)\b',
    _re.I | _re.UNICODE,
)


@st.cache_data(ttl=600)
def _load_visual_index() -> dict:
    if _USE_SUPABASE:
        rows = _sb_fetch_all("visual_index")
        return {r["url_key"]: r for r in rows if r.get("phash")}
    if not os.path.exists(VISUAL_INDEX):
        return {}
    with open(VISUAL_INDEX, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def _load_garimpo_resultados() -> dict:
    """Carrega resultados pré-calculados do Garimpo Visual (garimpo_resultados)."""
    if not _USE_SUPABASE:
        return {}
    rows = _sb_fetch_all("garimpo_resultados",
                         columns="url_detalhe,foto_url,artista,titulo,tecnica,dimensoes,lance_base,casa,data_leilao,similares,atualizado")
    return {r["url_detalhe"]: r for r in rows if r.get("url_detalhe")}


_RE_LIXO = _re.compile(
    r'^(none|null|n/a|na|s/n|-{1,3}|\.{1,3}|0)$'          # valores nulos/placeholder
    r'|tel\.?\s*\(?'                                         # número de telefone
    r'|\(\d{2}\)\s*\d'                                       # DDD + número
    r'|\d{4,5}[-.\s]\d{4}',                                  # padrão de telefone
    _re.I,
)

def _eh_desconhecido(artista: str) -> bool:
    art = str(artista).strip()
    if not art or len(art) <= 2:
        return True
    if _RE_DESCONHECIDO.search(art):
        return True
    if _RE_LIXO.search(art):
        return True
    return False


_RE_TECNICA_PALAVRA = _re.compile(
    r'\b(oleo|óleo|acril[íi]co|aquarela|guache|gouache|mista|sobre|'
    r'tela|madeira|papel|lona|cart[aã]o|s[eé]c|escola|arte|'
    r'sem|t[ií]tulo|lote|obra|pintura|desenho|escultura|gravura)\b',
    _re.I | _re.UNICODE,
)


def _match_assinatura(ocr_text: str, artista: str) -> int:
    """Retorna score 0-100 de quanto o texto OCR bate com o nome do artista."""
    if not ocr_text or not artista:
        return 0
    def _n(s):
        s = _ud.normalize("NFD", s.lower())
        return "".join(c for c in s if _ud.category(c) != "Mn")
    ocr_n   = _n(ocr_text)
    partes  = [p for p in _n(artista).split() if len(p) > 2]
    if not partes:
        return 0
    matches = sum(1 for p in partes if p in ocr_n)
    return round(matches / len(partes) * 100)


def _artista_do_titulo(titulo: str) -> str:
    """Tenta extrair nome de artista do título nos formatos:
      'NOME - descrição'  ou  'NOME. descrição'
    Retorna string vazia se não encontrar padrão de nome."""
    titulo = str(titulo or "").strip()
    # Tenta separadores: " - " e ". " (ponto seguido de espaço)
    candidato = ""
    for sep in (" - ", ". "):
        if sep in titulo:
            candidato = titulo.split(sep)[0].strip()
            break
    if not candidato:
        return ""
    # Descarta se contém palavras de técnica/descrição (não é nome de pessoa)
    if _RE_TECNICA_PALAVRA.search(candidato):
        return ""
    # Precisa ter 2+ palavras (nome e sobrenome)
    if len(candidato.split()) < 2:
        return ""
    # Descarta se for muito longa (provavelmente frase, não nome)
    if len(candidato) > 50:
        return ""
    return candidato


def _buscar_similares(foto_url: str, top_n: int = 5, max_dist: int = 18) -> list[dict]:
    """Compara foto_url contra o índice visual. Retorna top_n mais similares."""
    try:
        import imagehash
        import requests as _req
        from PIL import Image
        from io import BytesIO
    except ImportError:
        return []

    index = _load_visual_index()
    if not index:
        return []

    try:
        r = _req.get(foto_url, timeout=12,
                     headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
        if r.status_code != 200 or len(r.content) < 500:
            return []
        query_hash = imagehash.phash(Image.open(BytesIO(r.content)).convert("RGB"))
    except Exception:
        return []

    results = []
    for entry in index.values():
        try:
            dist = query_hash - imagehash.hex_to_hash(entry["phash"])
            if dist <= max_dist:
                sim = round(max(0, 100 - dist * 100 / 64))
                results.append({**entry, "similarity": sim, "dist": dist})
        except Exception:
            continue

    results.sort(key=lambda x: x["dist"])
    return results[:top_n]


def _prioridade_tecnica(tecnica: str) -> int:
    """Retorna prioridade de ordenação por técnica (menor = mais prioritário)."""
    t = tecnica.lower()
    if _re.search(r'\b(leo|leo sobre|oleo|óleo)\b', t): return 0   # óleo
    if _re.search(r'acr[ií]lic',  t): return 1                     # acrílico
    if _re.search(r'tempera|guach|gouache', t): return 2            # têmpera/guache
    if _re.search(r'aquarela|watercolor',  t): return 3             # aquarela
    if _re.search(r'pastel|grafite|crayon|giz', t): return 4        # seco
    if _re.search(r'mista|mixed',  t): return 5                     # técnica mista
    if t.strip():                          return 6                  # outra identificada
    return 7                                                         # sem técnica


def render_garimpo(df_leiloes):
    """Aba de garimpo: lotes vigentes com artista não identificado, confrontados com acervo visual."""

    def _realmente_desconhecido(row):
        if not _eh_desconhecido(row["artista"]):
            return False
        if _artista_do_titulo(row.get("titulo", "")):
            return False
        return True

    # Garante que só lotes com leilão ainda ativo aparecem (belt-and-suspenders)
    df_ativos = df_leiloes.copy()
    if "status" in df_ativos.columns:
        df_ativos = df_ativos[df_ativos["status"].isin(["ativo"]) | df_ativos["status"].isna()]
    if "data_leilao" in df_ativos.columns:
        df_ativos = df_ativos[~df_ativos["data_leilao"].apply(_data_leilao_passou)]

    df_desc = df_ativos[df_ativos.apply(_realmente_desconhecido, axis=1)].copy()
    df_desc["_prio"] = df_desc["tecnica"].apply(_prioridade_tecnica)

    resultados_pre = _load_garimpo_resultados()
    idx = _load_visual_index()
    _mh = load_media_hist()

    # ── Métricas ─────────────────────────────────────────────────────────────
    total_desc   = len(df_desc)
    com_foto     = (df_desc["foto_url"].str.strip() != "").sum()
    oleo_count   = (df_desc["_prio"] == 0).sum()
    com_similares = sum(
        1 for _, r in df_desc.iterrows()
        if resultados_pre.get(r.get("url_detalhe"), {}).get("similares")
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Não identificados", total_desc)
    c2.metric("Óleo / pintura", oleo_count)
    c3.metric("Com foto", com_foto)
    c4.metric("Com similar visual", com_similares)

    if df_desc.empty:
        st.info("Nenhum lote com artista não identificado em andamento.")
        return

    st.markdown("---")

    # ── Filtros ──────────────────────────────────────────────────────────────
    col_f1, col_f2, col_f3, col_f4, col_f5, col_f6 = st.columns([2, 2, 2, 2, 2, 2])
    with col_f1:
        filtro_tec = st.selectbox("Técnica",
            ["Todas", "Óleo", "Acrílico", "Aquarela", "Mista", "Sem técnica"], key="g_tec")
    with col_f2:
        _casas = ["Todas"] + sorted(df_desc["casa"].replace("", pd.NA).dropna().unique().tolist())
        filtro_casa = st.selectbox("Casa", _casas, key="g_casa")
    with col_f3:
        filtro_similar = st.selectbox("Similar", ["Todos", "Com similar", "Sem similar"], key="g_sim")
    with col_f4:
        ordem = st.selectbox("Ordenar por",
            ["Técnica + base", "Maior base", "Menor base", "Maior potencial"], key="g_ordem")
    with col_f5:
        _bases = df_desc["lance_base"][df_desc["lance_base"] > 0]
        _bmax  = int(_bases.max()) if len(_bases) else 50000
        preco_max = st.number_input("Base máx (R$)", value=_bmax, step=500, key="g_preco")
    with col_f6:
        # Tamanho: categorias por área em cm²
        # P  < 2.500 cm²   (~50×50 ou menor)
        # M  2.500–10.000  (~50×50 a 100×100)
        # G  10.000–40.000 (~100×100 a 200×200)
        # GG > 40.000      (> 200×200)
        filtro_tam = st.selectbox("Tamanho",
            ["Todos", "P – até 50×50", "M – até 100×100", "G – até 200×200", "GG – acima de 200×200", "Sem dimensão"],
            key="g_tam")

    # Aplica filtros
    df_g = df_desc.copy()
    _tec_map = {"Óleo": 0, "Acrílico": 1, "Aquarela": 3, "Mista": 5, "Sem técnica": 7}
    if filtro_tec in _tec_map:
        df_g = df_g[df_g["_prio"] == _tec_map[filtro_tec]]
    if filtro_casa != "Todas":
        df_g = df_g[df_g["casa"] == filtro_casa]
    if filtro_similar == "Com similar":
        df_g = df_g[df_g["url_detalhe"].apply(lambda u: bool(resultados_pre.get(u, {}).get("similares")))]
    elif filtro_similar == "Sem similar":
        df_g = df_g[~df_g["url_detalhe"].apply(lambda u: bool(resultados_pre.get(u, {}).get("similares")))]
    if preco_max > 0:
        df_g = df_g[(df_g["lance_base"] <= preco_max) | (df_g["lance_base"] == 0)]
    if filtro_tam != "Todos":
        _TAM_RANGES = {
            "P – até 50×50":      (0,       2_500),
            "M – até 100×100":    (2_500,  10_000),
            "G – até 200×200":    (10_000, 40_000),
            "GG – acima de 200×200": (40_000, float("inf")),
        }
        if filtro_tam == "Sem dimensão":
            df_g = df_g[df_g["dimensoes"].apply(lambda d: _parse_area_cm2(d) is None)]
        else:
            _amin, _amax = _TAM_RANGES[filtro_tam]
            def _tam_ok(d):
                a = _parse_area_cm2(d)
                return a is not None and _amin <= a < _amax
            df_g = df_g[df_g["dimensoes"].apply(_tam_ok)]

    # Calcula potencial para ordenação (com ajuste por área)
    def _calc_potencial(row):
        pre = resultados_pre.get(row.get("url_detalhe"), {})
        sims = pre.get("similares") or []
        if not sims: return 0
        melhor = sims[0]
        media = _mh.get(_norm_art(melhor["artista"]), {}).get("lance", 0) or melhor["maior_lance"]
        base  = row.get("lance_base", 0)
        # Ajuste por área: escala o preço de referência pela razão de tamanho
        area_lote = _parse_area_cm2(row.get("dimensoes", ""))
        area_sim  = _parse_area_cm2(melhor.get("dimensoes", ""))
        if area_lote and area_sim and area_sim > 0:
            media = media * (area_lote / area_sim)
        return round((media / base - 1) * 100) if media > base > 0 else 0

    if ordem == "Maior base":
        df_g = df_g.sort_values("lance_base", ascending=False)
    elif ordem == "Menor base":
        df_g = df_g.sort_values("lance_base", ascending=True)
    elif ordem == "Maior potencial":
        df_g["_pot"] = df_g.apply(_calc_potencial, axis=1)
        df_g = df_g.sort_values("_pot", ascending=False)
    else:
        df_g = df_g.sort_values(["_prio", "lance_base"], ascending=[True, False])

    total_filtrado = len(df_g)
    st.markdown(f"**{total_filtrado}** lotes encontrados")

    if df_g.empty:
        st.info("Nenhum resultado para os filtros selecionados.")
        return

    # ── Paginação ────────────────────────────────────────────────────────────
    POR_PAG = 20
    n_pags  = max(1, (total_filtrado + POR_PAG - 1) // POR_PAG)
    if "g_pag" not in st.session_state or st.session_state.get("g_pag", 1) > n_pags:
        st.session_state["g_pag"] = 1

    col_pag1, col_pag2, col_pag3 = st.columns([1, 3, 1])
    with col_pag1:
        if st.button("← Anterior", disabled=st.session_state["g_pag"] <= 1, key="g_prev"):
            st.session_state["g_pag"] -= 1
    with col_pag2:
        st.markdown(
            f'<div style="text-align:center;font-size:13px;padding-top:6px">'
            f'Página {st.session_state["g_pag"]} de {n_pags}</div>',
            unsafe_allow_html=True)
    with col_pag3:
        if st.button("Próxima →", disabled=st.session_state["g_pag"] >= n_pags, key="g_next"):
            st.session_state["g_pag"] += 1

    ini = (st.session_state["g_pag"] - 1) * POR_PAG
    df_pag = df_g.iloc[ini: ini + POR_PAG]

    st.markdown("---")

    # ── Grid 2 colunas ───────────────────────────────────────────────────────
    _TECS = {0:"🎨 Óleo", 1:"🖌 Acrílico", 2:"🖼 Têmpera", 3:"💧 Aquarela",
             4:"✏️ Seco", 5:"🔀 Mista", 6:"🖼 Outra", 7:""}

    lotes_lista = list(df_pag.iterrows())
    for i in range(0, len(lotes_lista), 2):
        cols = st.columns(2, gap="medium")
        for j, col in enumerate(cols):
            if i + j >= len(lotes_lista):
                break
            _, lote = lotes_lista[i + j]

            url     = lote.get("url_detalhe", "")
            foto    = lote.get("foto_url", "")
            titulo  = lote.get("titulo", "") or "Sem título"
            tecnica = lote.get("tecnica", "") or ""
            dims    = lote.get("dimensoes", "") or ""
            base    = lote.get("lance_base", 0)
            casa    = lote.get("casa", "")
            data    = lote.get("data_leilao", "") or ""
            prio    = int(lote.get("_prio", 7))
            tec_badge = _TECS.get(prio, "")

            pre      = resultados_pre.get(url)
            similares = (pre.get("similares") or []) if pre else None

            # Identificação automática (similaridade ≥ 80%)
            artista_sugerido = ""
            confianca = 0
            if similares:
                melhor = similares[0]
                confianca = melhor.get("similarity", 0)
                if confianca >= 80:
                    artista_sugerido = melhor["artista"]

            # Potencial (com ajuste por área se dimensões disponíveis)
            potencial = 0
            media_melhor = 0
            media_ajustada = 0
            artista_ref = ""
            area_ajuste_tag = ""
            if similares:
                melhor = similares[0]
                media_melhor = _mh.get(_norm_art(melhor["artista"]), {}).get("lance", 0) or melhor["maior_lance"]
                artista_ref  = melhor["artista"]
                # Ajuste por área
                area_lote = _parse_area_cm2(dims)
                area_sim  = _parse_area_cm2(melhor.get("dimensoes", ""))
                if area_lote and area_sim and area_sim > 0:
                    media_ajustada = media_melhor * (area_lote / area_sim)
                    area_ajuste_tag = f" (área ajustada)"
                else:
                    media_ajustada = media_melhor
                if media_ajustada > base > 0:
                    potencial = round((media_ajustada / base - 1) * 100)

            with col:
                # Assinatura OCR
                assinatura_ocr = (pre.get("assinatura_ocr") or "") if pre else ""
                ocr_match = _match_assinatura(assinatura_ocr, artista_sugerido) if artista_sugerido else 0

                # Badge de identificação acima do card
                if artista_sugerido:
                    if ocr_match >= 60:
                        ocr_tag = f' &nbsp;·&nbsp; ✅ Assinatura confere ({ocr_match}%)'
                        badge_bg = "#145a32"
                    elif ocr_match >= 30:
                        ocr_tag = f' &nbsp;·&nbsp; ⚠️ Assinatura parcial ({ocr_match}%)'
                        badge_bg = "#1d6a8a"
                    elif assinatura_ocr:
                        ocr_tag = f' &nbsp;·&nbsp; ❓ Assinatura: "{assinatura_ocr[:30]}"'
                        badge_bg = "#1d6a8a"
                    else:
                        ocr_tag = ""
                        badge_bg = "#1d6a8a"
                    st.markdown(
                        f'<div style="background:{badge_bg};color:#fff;border-radius:6px 6px 0 0;'
                        f'padding:5px 10px;font-size:12px;font-weight:600">'
                        f'🎯 Possível artista: {artista_sugerido} &nbsp;·&nbsp; {confianca}%{ocr_tag}</div>',
                        unsafe_allow_html=True)
                elif potencial >= 50:
                    _pot_area_tag = area_ajuste_tag if area_ajuste_tag else ""
                    st.markdown(
                        f'<div style="background:#1d7a4a;color:#fff;border-radius:6px 6px 0 0;'
                        f'padding:5px 10px;font-size:12px;font-weight:600">'
                        f'💎 +{potencial}% potencial{_pot_area_tag} · ref: {artista_ref}</div>',
                        unsafe_allow_html=True)

                radius_top = "0 0" if (artista_sugerido or potencial >= 50) else "6px 6px"

                # Foto do lote
                if foto:
                    st.markdown(
                        f'<img src="{foto}" referrerpolicy="no-referrer" '
                        f'style="width:100%;height:200px;object-fit:cover;'
                        f'border-radius:{radius_top} 0 0;display:block" '
                        f'onerror="this.style.opacity=\'0.2\'">',
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div style="width:100%;height:120px;background:#dde8f0;'
                        f'border-radius:{radius_top} 0 0;display:flex;align-items:center;'
                        f'justify-content:center;color:#7a9aaa;font-size:13px">Sem foto</div>',
                        unsafe_allow_html=True)

                # Info do card
                info_parts = [x for x in [tecnica, dims] if x]
                meta = " · ".join(info_parts) if info_parts else "—"
                url_html = f'<a href="{url}" target="_blank" style="color:#4a8fa8;font-size:12px">Ver lote ↗</a>' if url else ""
                # R$/m² do lote atual (baseado no lance_base)
                rpm2_lote = _r_por_m2(base, dims) if base and dims else None
                rpm2_html = (
                    f'<span style="font-size:11px;color:#3a7a5e;font-weight:600">'
                    f'📐 {fmt_m2(rpm2_lote)}</span>'
                ) if rpm2_lote else ""
                # Estimativa ajustada por área
                est_html = ""
                if media_ajustada and media_ajustada != media_melhor and base > 0:
                    est_html = (
                        f'<div style="font-size:11px;color:#1d7a4a;margin-top:2px">'
                        f'Estimativa área-ajustada: <b>{fmt_brl(media_ajustada)}</b></div>'
                    )
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #b8d0de;border-top:none;'
                    f'border-radius:0 0 6px 6px;padding:10px 12px">'
                    f'<div style="font-size:11px;color:#4a8fa8;margin-bottom:2px">{tec_badge} {casa}</div>'
                    f'<div style="font-weight:600;font-size:14px;margin-bottom:4px;line-height:1.3">{titulo[:65]}</div>'
                    f'<div style="font-size:11px;color:#3a5a6e;margin-bottom:6px">{meta}</div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<span style="font-size:14px;font-weight:700;color:#1a2a35">{fmt_brl(base)}</span>'
                    f'{rpm2_html}'
                    f'<span style="font-size:11px;color:#5a7a8e">{data}</span>'
                    f'</div>'
                    f'{est_html}'
                    f'<div style="margin-top:4px">{url_html}</div>'
                    f'</div>',
                    unsafe_allow_html=True)

                # Similares com foto de comparação
                if similares is None and foto and idx:
                    with st.spinner(""):
                        similares = _buscar_similares(foto, top_n=3, max_dist=20)

                if similares:
                    with st.expander(f"🔍 {len(similares)} similar(es)", expanded=False):
                        if pre and pre.get("atualizado"):
                            st.caption(f"Atualizado: {pre['atualizado'][:10]}")
                        for s in similares:
                            art_norm   = _norm_art(s["artista"])
                            media      = _mh.get(art_norm, {}).get("lance", 0) or s["maior_lance"]
                            sim_color  = "#1d6a8a" if s["similarity"] >= 80 else ("#1d7a4a" if s["similarity"] >= 65 else "#7a9aaa")
                            # R$/m² do similar
                            rpm2_sim = _r_por_m2(s["maior_lance"], s.get("dimensoes", ""))
                            rpm2_sim_txt = f" · 📐 {fmt_m2(rpm2_sim)}" if rpm2_sim else ""
                            # Estimativa área-ajustada para este lote
                            area_sim_s = _parse_area_cm2(s.get("dimensoes", ""))
                            area_lote_s = _parse_area_cm2(dims)
                            est_s = ""
                            if area_sim_s and area_lote_s and area_sim_s > 0 and media:
                                estimado_s = media * (area_lote_s / area_sim_s)
                                est_s = f'<br><span style="font-size:11px;color:#1d7a4a">→ Estimado p/ este lote: <b>{fmt_brl(estimado_s)}</b> (ajuste de área)</span>'
                            # Foto do similar ao lado das infos
                            sc1, sc2 = st.columns([1, 2])
                            with sc1:
                                if s.get("foto_url"):
                                    st.markdown(
                                        f'<img src="{s["foto_url"]}" referrerpolicy="no-referrer" '
                                        f'style="width:100%;border-radius:4px;object-fit:cover;max-height:90px" '
                                        f'onerror="this.style.display=\'none\'">',
                                        unsafe_allow_html=True)
                            with sc2:
                                st.markdown(
                                    f'<span style="color:{sim_color};font-weight:700;font-size:14px">{s["similarity"]}%</span><br>'
                                    f'<b style="font-size:13px">{s["artista"]}</b><br>'
                                    f'<span style="font-size:11px;color:#3a5a6e">{s["titulo"][:45]}</span><br>'
                                    f'<span style="font-size:11px">{s["tecnica"][:30]} · {s.get("dimensoes","")[:25]}</span><br>'
                                    f'<span style="font-size:12px">Hist.: <b>{fmt_brl(s["maior_lance"])}</b>'
                                    f'{f" · Média: <b>{fmt_brl(media)}</b>" if media else ""}'
                                    f'{rpm2_sim_txt}</span>'
                                    f'{est_s}',
                                    unsafe_allow_html=True)
                            st.markdown('<hr style="margin:6px 0;border-color:#b8d0de">', unsafe_allow_html=True)
                elif foto and similares is not None:
                    st.caption("Sem similar no índice.")

                # Mostra assinatura OCR mesmo sem similar
                if assinatura_ocr and not artista_sugerido:
                    st.markdown(
                        f'<div style="font-size:11px;color:#3a5a6e;margin-top:4px">'
                        f'✍️ Texto detectado na tela: <i>{assinatura_ocr[:80]}</i></div>',
                        unsafe_allow_html=True)

                st.markdown("")  # espaçamento entre linhas


# ── Favoritos & Watchlist ───────────────────────────────────────────────────
_FAV_FILE   = os.path.join(_DIR, "favoritos.json")
_WATCH_FILE = os.path.join(_DIR, "watchlist.json")


def _load_json_set(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_json_set(path, s):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f, ensure_ascii=False)


def get_favoritos():
    if "favoritos" not in st.session_state:
        st.session_state["favoritos"] = _load_json_set(_FAV_FILE)
    return st.session_state["favoritos"]


def toggle_favorito(url):
    favs = get_favoritos()
    if url in favs:
        favs.discard(url)
    else:
        favs.add(url)
    _save_json_set(_FAV_FILE, favs)


def get_watchlist():
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = _load_json_set(_WATCH_FILE)
    return st.session_state["watchlist"]


def toggle_watch(artista_norm):
    wl = get_watchlist()
    if artista_norm in wl:
        wl.discard(artista_norm)
    else:
        wl.add(artista_norm)
    _save_json_set(_WATCH_FILE, wl)


# ── Análise de Mercado ───────────────────────────────────────────────────────
def render_mercado(df_hist):
    if df_hist.empty:
        st.info("Sem dados históricos para análise.")
        return

    df = df_hist.copy()
    df = df[df["maior_lance"] > 0]
    df["artista_norm"] = df["artista"].apply(_norm_art)

    # ── Ranking artistas ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Ranking de Artistas</div>', unsafe_allow_html=True)
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        rank_vol = (
            df.groupby("artista")
            .agg(obras=("maior_lance", "count"), total=("maior_lance", "sum"))
            .sort_values("obras", ascending=False)
            .head(20)
            .reset_index()
        )
        fig = px.bar(
            rank_vol, x="obras", y="artista", orientation="h",
            title="Top 20 — Volume de Obras Arrematadas",
            color="obras", color_continuous_scale="Oranges",
            labels={"obras": "Qtd. Obras", "artista": ""},
        )
        fig.update_layout(
            plot_bgcolor="#1a1a2e", paper_bgcolor="#1a1a2e",
            font_color="#c0c0d8", yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False, height=480,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r2:
        rank_val = (
            df.groupby("artista")
            .agg(media=("maior_lance", "mean"), obras=("maior_lance", "count"))
            .query("obras >= 2")
            .sort_values("media", ascending=False)
            .head(20)
            .reset_index()
        )
        rank_val["media_fmt"] = rank_val["media"].apply(lambda v: f"R$ {v:,.0f}")
        fig2 = px.bar(
            rank_val, x="media", y="artista", orientation="h",
            title="Top 20 — Maior Arremate Médio (mín. 2 obras)",
            color="media", color_continuous_scale="Purples",
            labels={"media": "Arremate Médio R$", "artista": ""},
        )
        fig2.update_layout(
            plot_bgcolor="#1a1a2e", paper_bgcolor="#1a1a2e",
            font_color="#c0c0d8", yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False, height=480,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Base vs Arremate ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Base Pedida × Arremate Real</div>', unsafe_allow_html=True)
    df_base = df[(df["lance_base"] > 0) & (df["maior_lance"] > 0)].copy()
    df_base["fator"] = (df_base["maior_lance"] / df_base["lance_base"]).round(2)
    art_base = (
        df_base.groupby("artista")
        .agg(base_media=("lance_base", "mean"), arr_media=("maior_lance", "mean"),
             fator_medio=("fator", "mean"), obras=("maior_lance", "count"))
        .query("obras >= 2")
        .reset_index()
    )
    if not art_base.empty:
        fig3 = px.scatter(
            art_base, x="base_media", y="arr_media", size="obras",
            hover_name="artista", color="fator_medio",
            color_continuous_scale="RdYlGn",
            labels={"base_media": "Base Média R$", "arr_media": "Arremate Médio R$",
                    "fator_medio": "Fator", "obras": "Obras"},
            title="Artistas — Base pedida vs. Arremate (tamanho = volume de obras)",
        )
        fig3.add_shape(type="line", x0=0, y0=0,
                       x1=art_base["base_media"].max(), y1=art_base["base_media"].max(),
                       line=dict(color="#666", dash="dot"))
        fig3.update_layout(
            plot_bgcolor="#1a1a2e", paper_bgcolor="#1a1a2e",
            font_color="#c0c0d8", height=460,
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── Termômetro por Casa ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">Desempenho por Casa de Leilão</div>', unsafe_allow_html=True)
    df_casa = df_hist[df_hist["casa"].str.strip() != ""].copy()
    df_casa["arrematado"] = df_casa["maior_lance"] > 0
    termo = (
        df_casa.groupby("casa")
        .agg(total=("maior_lance", "count"),
             arr=("arrematado", "sum"),
             arr_medio=("maior_lance", "mean"))
        .query("total >= 3")
        .reset_index()
    )
    termo["pct"] = (termo["arr"] / termo["total"] * 100).round(1)
    termo = termo.sort_values("pct", ascending=False).head(25)
    fig4 = px.bar(
        termo, x="pct", y="casa", orientation="h",
        color="pct", color_continuous_scale="Greens",
        title="Taxa de Arremate por Casa (% lotes vendidos, mín. 3 históricos)",
        labels={"pct": "% Arrematados", "casa": "", "total": "Total"},
        hover_data={"total": True, "arr": True},
    )
    fig4.update_layout(
        plot_bgcolor="#1a1a2e", paper_bgcolor="#1a1a2e",
        font_color="#c0c0d8", yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False, height=max(350, len(termo) * 22),
    )
    st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
_fundo_css = f"background-image: url('data:image/png;base64,{_FUNDO_B64}');" if _FUNDO_B64 else "background: #d8e8ee;"
st.markdown(f"""
<div class="hero" style="{_fundo_css}">
  <div class="hero-overlay">
    <p class="hero-title">Art Radar</p>
    <p class="hero-sub">Leilões &nbsp;·&nbsp; Histórico &nbsp;·&nbsp; Inteligência de Mercado</p>
  </div>
</div>
""", unsafe_allow_html=True)

col_tabs, col_refresh = st.columns([10, 1])
with col_tabs:
    aba1, aba2, aba3, aba4, aba5 = st.tabs([
        "  🔨  Em Leilão  ",
        "  📈  Histórico  ",
        "  📊  Mercado  ",
        "  ★  Favoritos  ",
        "  🔍  Garimpo  ",
    ])
with col_refresh:
    if st.button("↺", help="Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── ABA 1: Em Leilão Agora ────────────────────────────────────────────────────
with aba1:
    df_leiloes = load_leiloes()

    if df_leiloes.empty:
        st.warning("Base de dados vazia. Rode `catalogo_leiloesbr.py` primeiro.")
    else:
        total     = len(df_leiloes)
        com_lance = (df_leiloes["maior_lance"] > 0).sum()
        com_foto  = (df_leiloes["foto_url"] != "").sum()
        artistas  = df_leiloes["artista"].replace("", pd.NA).dropna().nunique()
        casas     = df_leiloes["casa"].replace("", pd.NA).dropna().nunique()

        # Cobertura de preços
        _arts_tuple = tuple(sorted(df_leiloes["artista"].replace("", pd.NA).dropna().unique()))
        _cob_com, _cob_sem, _cob_tot, _cob_pct, _cob_sem_lista = _cobertura_precos(_arts_tuple)
        _cob_color = "#22c55e" if _cob_pct >= 60 else ("#f59e0b" if _cob_pct >= 30 else "#ef4444")

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        for col, label, val in [
            (c1, "Lotes Ativos", total),
            (c2, "Com Lance",    com_lance),
            (c3, "Com Foto",     com_foto),
            (c4, "Artistas",     artistas),
            (c5, "Casas",        casas),
        ]:
            col.markdown(
                f'<div class="mbox"><div class="mlabel">{label}</div>'
                f'<div class="mvalue">{val}</div></div>',
                unsafe_allow_html=True,
            )
        c6.markdown(
            f'<div class="mbox" style="border-color:{_cob_color}44">'
            f'<div class="mlabel">Cobertura de Preços</div>'
            f'<div class="mvalue" style="color:{_cob_color}">{_cob_pct}%</div>'
            f'<div class="msub">{_cob_com} de {_cob_tot} artistas referenciados</div>'
            f'<div class="mprog-wrap"><div style="width:{_cob_pct}%;height:5px;'
            f'background:{_cob_color};border-radius:4px"></div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )


        st.markdown('<div class="section-title">Filtros</div>', unsafe_allow_html=True)
        fa, fa_norm, ft, fc, fass, ffoto, fbase, preco_range = render_filtros(df_leiloes, prefix="L", campo_preco="lance_base")

        col_r, col_d2, col_o, col_v = st.columns([2, 2, 2, 2])
        with col_r:
            filtro_lance = st.selectbox("Lances", ["Todos", "Com lance", "Sem lance"], key="L_lances")
        with col_d2:
            # Datas únicas de leilão, ordenadas
            _datas_raw = df_leiloes["data_leilao"].dropna().astype(str)
            _datas_raw = _datas_raw[_datas_raw.str.match(r'\d{1,2}/\d{1,2}/\d{4}')]
            _datas_unicas = sorted(
                _datas_raw.unique().tolist(),
                key=lambda d: (int(d.split("/")[2]), int(d.split("/")[1]), int(d.split("/")[0]))
            )
            filtro_data = st.selectbox(
                "Data do Leilão",
                ["Todas as datas"] + _datas_unicas,
                key="L_data",
            )
        with col_o:
            ordem = st.selectbox(
                "Ordenar",
                ["Rentabilidade ↓", "Data ↑", "Maior Lance ↓", "Valor Base ↓", "Artista (A-Z)", "Qtd. Lances ↓"],
                key="L_ordem",
            )
        with col_v:
            modo_exib = st.selectbox(
                "Exibição",
                ["Cards", "Agrupar por artista", "Duplicatas"],
                key="L_modo",
            )

        df = aplicar_filtros(df_leiloes, fa, fa_norm, ft, fc, fass, ffoto, fbase, preco_range, campo_preco="lance_base")
        if filtro_lance == "Com lance":
            df = df[df["maior_lance"] > 0]
        elif filtro_lance == "Sem lance":
            df = df[df["maior_lance"] == 0]
        if filtro_data != "Todas as datas":
            df = df[df["data_leilao"] == filtro_data]

        # Coluna de rentabilidade para ordenação
        _mh = load_media_hist()
        df["_rent"] = df.apply(
            lambda r: ((((_mh.get(_norm_art(str(r["artista"])), {}).get("lance", 0) or
                          _mh.get(_norm_art(str(r["artista"])), {}).get("base", 0))) / r["lance_base"]) - 1) * 100
            if r["lance_base"] > 0 and (_mh.get(_norm_art(str(r["artista"])), {}).get("lance", 0) or
                                         _mh.get(_norm_art(str(r["artista"])), {}).get("base", 0))
            else -9999,
            axis=1,
        )

        if ordem == "Rentabilidade ↓":
            df = df.sort_values("_rent", ascending=False)
        elif ordem == "Artista (A-Z)":
            df = df.sort_values("artista", key=lambda s: s.str.lower())
        elif ordem == "Maior Lance ↓":
            df = df.sort_values("maior_lance", ascending=False)
        elif ordem == "Valor Base ↓":
            df = df.sort_values("lance_base", ascending=False)
        elif ordem == "Qtd. Lances ↓":
            df = df.sort_values("num_lances", ascending=False)
        elif ordem == "Data ↑":
            df = df.sort_values(
                "data_leilao",
                key=lambda s: pd.to_datetime(s, dayfirst=True, errors="coerce"),
                ascending=True,
                na_position="last",
            )

        st.markdown(f"**{len(df)}** resultado(s)")

        if df.empty:
            st.info("Nenhum resultado.")
        elif modo_exib == "Agrupar por artista":
            render_cards_por_artista(df.drop(columns=["_rent"], errors="ignore"))
        elif modo_exib == "Duplicatas":
            render_duplicatas(df.drop(columns=["_rent"], errors="ignore"))
        else:
            # Cards paginados (modo padrão)
            total_res = len(df)
            total_pag = max(1, (total_res + PER_PAGE - 1) // PER_PAGE)

            _fk = f"{fa_norm}|{ft}|{fc}|{fass}|{ffoto}|{fbase}|{preco_range}|{filtro_lance}|{filtro_data}|{ordem}"
            if st.session_state.get("L_fk") != _fk:
                st.session_state["L_fk"] = _fk
                st.session_state["L_pag"] = 1
            pag = st.session_state.get("L_pag", 1)
            pag = max(1, min(pag, total_pag))

            st.markdown(f"Página **{pag}** de **{total_pag}**")

            df_pag = df.iloc[(pag - 1) * PER_PAGE : pag * PER_PAGE]
            render_cards_leilao(df_pag)

            st.markdown("---")
            cp, ci, cn = st.columns([1, 3, 1])
            with cp:
                if st.button("← Anterior", disabled=(pag <= 1), key="L_prev", use_container_width=True):
                    st.session_state["L_pag"] = pag - 1
                    st.rerun()
            with ci:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px;color:#888'>"
                    f"Página {pag} / {total_pag}</div>",
                    unsafe_allow_html=True,
                )
            with cn:
                if st.button("Próxima →", disabled=(pag >= total_pag), key="L_next", use_container_width=True):
                    st.session_state["L_pag"] = pag + 1
                    st.rerun()

            with st.expander("📊 Resumo por Artista"):
                render_resumo_artista(df)


# ── ABA 2: Histórico de Preços ────────────────────────────────────────────────
with aba2:
    df_hist = load_historico()

    if df_hist.empty:
        st.warning("Base histórica vazia. Rode `catalogo_bolsadearte.py` e/ou `catalogo_cda.py` primeiro.")
    else:
        total     = len(df_hist)
        com_lance = (df_hist["maior_lance"] > 0).sum()
        com_est   = (df_hist["estimativa_min"] > 0).sum()
        com_foto  = (df_hist["foto_url"] != "").sum()
        artistas  = df_hist["artista"].replace("", pd.NA).dropna().nunique()

        c1, c2, c3, c4, c5 = st.columns(5)
        for col, label, val in [
            (c1, "Obras",         total),
            (c2, "Com Lance",     com_lance),
            (c3, "Com Estimativa",com_est),
            (c4, "Com Foto",      com_foto),
            (c5, "Artistas",      artistas),
        ]:
            col.markdown(
                f'<div class="mbox"><div class="mlabel">{label}</div>'
                f'<div class="mvalue">{val}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="section-title">Filtros</div>', unsafe_allow_html=True)
        fa, fa_norm, ft, fc, fass, ffoto, fbase, preco_range = render_filtros(df_hist, prefix="H", campo_preco="maior_lance")

        col_r, col_o = st.columns([2, 2])
        with col_r:
            filtro_resultado = st.selectbox("Resultado", ["Todos", "Arrematados", "Sem lance"], key="H_resultado")
        with col_o:
            ordem = st.selectbox("Ordenar", ["Avaliação ↓", "% da Avaliação ↓", "Último Lance ↓", "Estimativa ↓", "Artista (A-Z)", "Data ↓"], key="H_ordem")

        df = aplicar_filtros(df_hist, fa, fa_norm, ft, fc, fass, ffoto, fbase, preco_range, campo_preco="maior_lance")
        if filtro_resultado == "Arrematados":
            df = df[df["maior_lance"] > 0]
        elif filtro_resultado == "Sem lance":
            df = df[df["maior_lance"] == 0]

        _mh_hist = load_media_hist()
        if ordem == "Avaliação ↓":
            df = df.copy()
            df["_aval_sort"] = df["artista"].apply(
                lambda a: _mh_hist.get(_norm_art(str(a)), {}).get("lance", 0) or
                          _mh_hist.get(_norm_art(str(a)), {}).get("base", 0))
            df = df.sort_values("_aval_sort", ascending=False)
        elif ordem == "% da Avaliação ↓":
            df = df.copy()
            def _pct_sort(r):
                av = (_mh_hist.get(_norm_art(str(r["artista"])), {}).get("lance", 0) or
                      _mh_hist.get(_norm_art(str(r["artista"])), {}).get("base", 0))
                return (r["maior_lance"] / av * 100) if av > 0 and r["maior_lance"] > 0 else -9999
            df["_pct_sort"] = df.apply(_pct_sort, axis=1)
            df = df.sort_values("_pct_sort", ascending=False)
        elif ordem == "Último Lance ↓":
            df = df.sort_values("maior_lance", ascending=False)
        elif ordem == "Estimativa ↓":
            df = df.sort_values("estimativa_max", ascending=False)
        elif ordem == "Artista (A-Z)":
            df = df.sort_values("artista", key=lambda s: s.str.lower())
        elif ordem == "Data ↓":
            df = df.sort_values("data_leilao", ascending=False)

        # Gráfico de evolução — aparece quando artista específico é buscado
        if fa.strip():
            render_grafico_artista(df_hist, fa)
            st.markdown("---")

        total_res = len(df)
        total_pag = max(1, (total_res + PER_PAGE - 1) // PER_PAGE)

        # Reset de página quando filtros mudam
        _fk = f"{fa_norm}|{ft}|{fc}|{fass}|{ffoto}|{fbase}|{preco_range}|{filtro_resultado}|{ordem}"
        if st.session_state.get("H_fk") != _fk:
            st.session_state["H_fk"] = _fk
            st.session_state["H_pag"] = 1
        pag = st.session_state.get("H_pag", 1)
        pag = max(1, min(pag, total_pag))

        st.markdown(f"**{total_res}** resultado(s) — página **{pag}** de **{total_pag}**")

        if df.empty:
            st.info("Nenhum resultado.")
        else:
            df_pag = df.iloc[(pag - 1) * PER_PAGE : pag * PER_PAGE]
            render_cards_historico(df_pag)

            # Navegação
            st.markdown("---")
            cp, ci, cn = st.columns([1, 3, 1])
            with cp:
                if st.button("← Anterior", disabled=(pag <= 1), key="H_prev", use_container_width=True):
                    st.session_state["H_pag"] = pag - 1
                    st.rerun()
            with ci:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px;color:#888'>"
                    f"Página {pag} / {total_pag}</div>",
                    unsafe_allow_html=True,
                )
            with cn:
                if st.button("Próxima →", disabled=(pag >= total_pag), key="H_next", use_container_width=True):
                    st.session_state["H_pag"] = pag + 1
                    st.rerun()

            with st.expander("📊 Resumo por Artista"):
                render_resumo_artista(df)

# ── ABA 3: Análise de Mercado ─────────────────────────────────────────────────
with aba3:
    df_hist_m = load_historico()
    df_lei_m  = load_leiloes()
    # Combina histórico com lotes ativos já arrematados para análise mais rica
    df_analise = df_hist_m.copy()
    render_mercado(df_analise)

# ── ABA 4: Favoritos & Watchlist ──────────────────────────────────────────────
with aba4:
    df_lei_fav = load_leiloes()

    # ── Watchlist de artistas ─────────────────────────────────────────────────
    st.markdown('<div class="section-title">Watchlist de Artistas</div>', unsafe_allow_html=True)
    wl = get_watchlist()
    wl_alertas = []
    if not df_lei_fav.empty:
        for art_norm in list(wl):
            match = df_lei_fav[df_lei_fav["artista"].apply(_norm_art) == art_norm]
            if not match.empty:
                wl_alertas.append((art_norm, match))

    if wl_alertas:
        for art_norm, match_df in wl_alertas:
            nome_disp = match_df["artista"].iloc[0]
            st.success(f"**{nome_disp}** está em leilão agora — {len(match_df)} lote(s)")

    col_wl_a, col_wl_b = st.columns([3, 1])
    with col_wl_a:
        novo_watch = st.text_input("Adicionar artista à watchlist", placeholder="ex: Di Cavalcanti", key="wl_input")
    with col_wl_b:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        if st.button("Adicionar", use_container_width=True, key="wl_add"):
            if novo_watch.strip():
                toggle_watch(_norm_art(novo_watch.strip()))
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if wl:
        st.markdown("**Monitorando:**")
        for art_norm in sorted(wl):
            c1, c2 = st.columns([5, 1])
            em_leilao = any(
                df_lei_fav[df_lei_fav["artista"].apply(_norm_art) == art_norm].shape[0] > 0
            ) if not df_lei_fav.empty else False
            with c1:
                _ind = "🟢 " if em_leilao else "⚪ "
                st.markdown(
                    f'<span style="color:#c0c0d8">{_ind}{art_norm}</span>',
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("✕", key=f"wl_rm_{hash(art_norm)}", help="Remover"):
                    toggle_watch(art_norm)
                    st.rerun()
    else:
        st.caption("Nenhum artista monitorado ainda.")

    st.markdown("---")

    # ── Lotes Favoritos ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Lotes Favoritos</div>', unsafe_allow_html=True)
    favs = get_favoritos()
    if not favs:
        st.info("Nenhum lote favoritado. Use o botão ☆ nos cards para salvar lotes.")
    else:
        if df_lei_fav.empty:
            st.warning("Base de lotes vazia.")
        else:
            _url_col = "url_detalhe"
            df_favs = df_lei_fav[df_lei_fav[_url_col].isin(favs)]
            _enc = [f for f in favs if f not in df_lei_fav[_url_col].values]
            if _enc:
                st.caption(f"{len(_enc)} lote(s) favoritado(s) já encerrado(s) / não encontrado(s) na base atual.")
            if df_favs.empty:
                st.info("Nenhum lote favorito está em leilão no momento.")
            else:
                st.markdown(f"**{len(df_favs)}** lote(s) favoritado(s) em leilão agora:")
                render_cards_leilao(df_favs)

        # Botão limpar favoritos encerrados
        _enc_count = len([f for f in favs if not df_lei_fav.empty and f not in df_lei_fav["url_detalhe"].values])
        if _enc_count > 0:
            if st.button(f"🗑️ Limpar {_enc_count} favorito(s) encerrado(s)", key="fav_limpar"):
                ativos_set = set(df_lei_fav["url_detalhe"].values) if not df_lei_fav.empty else set()
                new_favs = favs & ativos_set
                st.session_state["favoritos"] = new_favs
                _save_json_set(_FAV_FILE, new_favs)
                st.rerun()


# ── ABA 5: Garimpo Visual ─────────────────────────────────────────────────────
with aba5:
    df_lei_garimpo = load_leiloes()
    render_garimpo(df_lei_garimpo)
