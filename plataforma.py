#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plataforma de Arte — Leilões & Histórico de Preços
Execute com:  streamlit run plataforma.py --server.address localhost
"""

import hashlib
import io
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
    [data-testid="stAppViewContainer"] { background: #0f0f1a; }
    [data-testid="stSidebar"] { display: none; }
    .login-box {
        max-width: 380px; margin: 8vh auto 0;
        background: #1a1a2e; border: 1px solid #2e2e4a;
        border-radius: 16px; padding: 48px 40px 40px;
        box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .login-logo { font-size: 2.4rem; text-align: center; margin-bottom: 6px; }
    .login-title { color: #c9a96e; font-size: 1.3rem; font-weight: 700;
                   text-align: center; letter-spacing: .06em; margin-bottom: 28px; }
    </style>
    <div class="login-box">
      <div class="login-logo">🖼️</div>
      <div class="login-title">ARTE EM LEILÃO</div>
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
    page_title="Arte em Leilão",
    page_icon="🖼️",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Inter:wght@300;400;500;600&display=swap');

/* ── Reset & base ── */
[data-testid="stAppViewContainer"] {
    background: #1a1a2e;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #1e1e32 !important; }
section[data-testid="stMain"] > div { padding-top: 0 !important; }
.block-container { padding: 0 2rem 2rem 2rem !important; max-width: 1400px; }

/* ── Hero header com pintura abstrata SVG ── */
.hero {
    position: relative;
    width: 100%;
    border-radius: 0 0 24px 24px;
    overflow: hidden;
    margin-bottom: 2rem;
}
.hero-bg {
    display: block;
    width: 100%;
    height: 220px;
}
.hero-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        to bottom,
        rgba(8,8,16,0.15) 0%,
        rgba(8,8,16,0.55) 60%,
        rgba(8,8,16,0.92) 100%
    );
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    padding-bottom: 28px;
}
.hero-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 48px;
    font-weight: 300;
    color: #f5e6c8;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    line-height: 1;
    margin: 0;
    text-shadow: 0 2px 30px rgba(0,0,0,0.8);
}
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 300;
    color: rgba(245,230,200,0.55);
    letter-spacing: 0.35em;
    text-transform: uppercase;
    margin-top: 8px;
}

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #1e1e30 !important;
    gap: 0 !important;
}
[data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    color: #555 !important;
    padding: 12px 28px !important;
    background: transparent !important;
    border: none !important;
    text-transform: uppercase !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #c9a96e !important;
    border-bottom: 2px solid #c9a96e !important;
}
[data-baseweb="tab-highlight"] { display: none !important; }
[data-baseweb="tab-border"]    { display: none !important; }

/* ── Metric boxes ── */
.mbox {
    background: linear-gradient(135deg, #22223a 0%, #1e1e34 100%);
    border: 1px solid #2e2e4a;
    border-radius: 14px;
    padding: 18px 12px;
    text-align: center;
    transition: border-color .25s, transform .25s;
}
.mbox:hover { border-color: #c9a96e88; transform: translateY(-2px); }
.msub {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: #5a5a7a;
    margin-top: 5px;
    letter-spacing: 0.04em;
}
.mprog-wrap {
    background: #12122a;
    border-radius: 4px;
    height: 5px;
    margin-top: 10px;
    overflow: hidden;
}
.mlabel {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 500;
    color: #7878a0;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.mvalue {
    font-family: 'Cormorant Garamond', serif;
    font-size: 32px;
    font-weight: 300;
    color: #c9a96e;
    line-height: 1;
}

/* ── Section title ── */
.section-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 22px;
    font-weight: 300;
    color: #f0e0c0;
    letter-spacing: 0.08em;
    margin: 1.5rem 0 1rem;
    padding-bottom: 8px;
    border-bottom: 1px solid #2e2e48;
}

/* ── Cards ── */
.card {
    border: 1px solid #2a2a42;
    border-radius: 16px;
    overflow: hidden;
    background: #1e1e32;
    margin-bottom: 20px;
    transition: border-color .3s, box-shadow .3s, transform .3s;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.card:hover {
    border-color: #c9a96e66;
    box-shadow: 0 8px 36px rgba(201,169,110,0.12);
    transform: translateY(-3px);
}
.card-img {
    width: 100%;
    aspect-ratio: 4/3;
    object-fit: cover;
    display: block;
    background: #16162a;
}
.card-img-placeholder {
    width: 100%;
    aspect-ratio: 4/3;
    background: linear-gradient(135deg, #1a1a2e 0%, #20203a 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #2e2e48;
    font-size: 42px;
}
.card-body { padding: 16px; }
.card-casa {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    font-weight: 500;
    color: #5a5a7a;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.card-artista {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 700;
    color: #f0e0c0;
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
    color: #c8c0d8;
    text-transform: lowercase;
    margin-bottom: 8px;
    padding-top: 4px;
    border-top: 1px solid #2a2a42;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.card-meta {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    color: #5a5a7a;
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
    background: #16162a;
    border: 1px solid #2a2a42;
    border-radius: 10px;
    padding: 10px 6px;
    text-align: center;
}
.price-label {
    font-family: 'Inter', sans-serif;
    font-size: 8px;
    font-weight: 500;
    color: #5a5a7a;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.price-val-base  { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #7ec8e3; }
.price-val-lance { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #7dd4a0; }
.price-val-est   { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #c9a96e; }
.price-val-aval  { font-family: 'Cormorant Garamond', serif; font-size: 16px; font-weight: 600; color: #a78bfa; }
.price-val-aval-vazio { font-family: 'Inter', sans-serif; font-size: 11px; color: #3a3a5a; }
.card-data-leilao {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 600;
    color: #c9a96e;
    background: rgba(201,169,110,0.10);
    border: 1px solid rgba(201,169,110,0.25);
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
.rent-alto  { background: rgba(74,222,128,0.12); color: #4ade80; border: 1px solid rgba(74,222,128,0.3); }
.rent-medio { background: rgba(250,204,21,0.10); color: #facc15; border: 1px solid rgba(250,204,21,0.25); }
.rent-baixo { background: rgba(248,113,113,0.10); color: #f87171; border: 1px solid rgba(248,113,113,0.25); }
.rent-none  { background: rgba(100,100,120,0.08); color: #4a4a6a; border: 1px solid rgba(100,100,120,0.2); font-size: 11px; font-weight: 400; }
.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 4px;
}
.card-date {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    color: #44446a;
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
.badge-lance   { background: rgba(40,120,75,0.3);   color: #6dcf90; border: 1px solid #2a6a40; }
.badge-vendida { background: rgba(40,90,160,0.3);   color: #6aaae0; border: 1px solid #2a5090; }
.badge-semlan  { background: rgba(50,50,80,0.5);    color: #6666888; border: 1px solid #333355; }
.badge-ass     { background: rgba(100,80,30,0.35);  color: #c9a96e; border: 1px solid #6a5a28; margin-left: 5px; }
.badge-nass    { background: rgba(120,40,40,0.35);  color: #d47878; border: 1px solid #6a2828; margin-left: 5px; }
.badge-mono    { background: rgba(80,50,130,0.35);  color: #aa80e0; border: 1px solid #4a2878; margin-left: 5px; }
.card-link { margin-top: 10px; }
.card-link a {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 500;
    color: #5588cc !important;
    text-decoration: none;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.card-link a:hover { color: #c9a96e !important; }

/* ── Divider ── */
hr { border: none; border-top: 1px solid #26263e; margin: 1.5rem 0; }

/* ── Inputs e selects ── */
[data-baseweb="input"] input,
[data-baseweb="select"] div {
    background: #22223a !important;
    border-color: #2e2e4a !important;
    color: #ddd !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
label[data-testid="stWidgetLabel"] p {
    font-family: 'Inter', sans-serif !important;
    font-size: 10px !important;
    font-weight: 500 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: #7070a0 !important;
}
[data-testid="stCheckbox"] label p {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    color: #9090b8 !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #1e1e32 !important;
    border: 1px solid #2a2a42 !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary {
    color: #9090b8 !important;
}
/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #2a2a42 !important;
}
[data-baseweb="tab"] {
    color: #7070a0 !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #c9a96e !important;
    border-bottom: 2px solid #c9a96e !important;
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
    """Média histórica de preços por artista. Retorna dict norm_name → média (int)."""
    hist = {}

    if _USE_SUPABASE:
        # Busca apenas campos necessários para economizar dados
        rows = _sb_fetch_all("lotes", filters={"em_leilao": False},
                             columns="artista,maior_lance")
        for v in rows:
            art = _norm_art(v.get("artista", ""))
            if not art: continue
            p = v.get("maior_lance") or 0
            try:
                p = float(p)
            except Exception:
                p = 0
            if p > 0:
                hist.setdefault(art, []).append(p)
        # Histórico Levy + Conrad
        hcf_rows = _sb_fetch_all("historico_casas", columns="artista,maior_lance")
        for v in hcf_rows:
            art = _norm_art(v.get("artista", ""))
            if not art: continue
            p = v.get("maior_lance") or 0
            try:
                p = float(p)
            except Exception:
                p = 0
            if p > 0:
                hist.setdefault(art, []).append(p)
        return {art: round(sum(ps) / len(ps)) for art, ps in hist.items() if ps}

    # ── Fallback: leitura local ──────────────────────────────────────────────
    for arq in [BDA_FILE, CDA_FILE]:
        if not os.path.exists(arq): continue
        with open(arq, "r", encoding="utf-8") as f:
            d = json.load(f)
        for v in d.values():
            if not isinstance(v, dict): continue
            art = _norm_art(v.get("artista", ""))
            if not art: continue
            p = v.get("maior_lance") or v.get("lance_atual") or 0
            try: p = float(p)
            except Exception: p = 0
            if p > 0: hist.setdefault(art, []).append(p)
    for arq in [DB_FILE, ARR_FILE]:
        if not os.path.exists(arq): continue
        with open(arq, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if not isinstance(v, dict) or v.get("em_leilao") is not False: continue
            art = _norm_art(v.get("artista", ""))
            if not art: continue
            p = v.get("maior_lance") or 0
            try: p = float(p)
            except Exception: p = 0
            if p > 0: hist.setdefault(art, []).append(p)
    if os.path.exists(HCF_FILE):
        with open(HCF_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        for v in d.get("lotes", []):
            if not isinstance(v, dict): continue
            art = _norm_art(v.get("artista", ""))
            if not art: continue
            p = v.get("maior_lance", 0)
            try: p = float(p)
            except Exception: p = 0
            if p > 0: hist.setdefault(art, []).append(p)
    return {art: round(sum(ps) / len(ps)) for art, ps in hist.items() if ps}


def fmt_brl(v):
    if v and v > 0:
        return f"R$ {v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "—"


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
        _labels     = ["— Todos os artistas —"] + [o[2] for o in _opcoes]
        _principals = [""]                       + [o[1] for o in _opcoes]
        _norms      = [""]                       + [o[0] for o in _opcoes]
        _sel = st.selectbox(
            "Artista",
            range(len(_labels)),
            format_func=lambda i: _labels[i],
            key=f"{prefix}_artista",
        )
        busca_artista       = _principals[_sel]   # nome canônico ou ""
        busca_artista_norm  = _norms[_sel]         # norm para filtro exato
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
        # Compara pela forma normalizada — agrupa "José Flores" e "José das Flores"
        df = df[df["artista"].apply(lambda x: _norm_art(str(x))) == busca_artista_norm]
    elif busca_artista.strip():
        df = df[df["artista"].str.contains(busca_artista.strip(), case=False, na=False)]
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
            _art_norm  = _norm_art(artista)
            _aval_val  = media_hist.get(_art_norm, 0)
            _base_val  = item["lance_base"]
            aval_str   = fmt_brl(_aval_val)
            aval_css   = "price-val-aval" if _aval_val > 0 else "price-val-aval-vazio"
            aval_disp  = aval_str if _aval_val > 0 else "sem histórico"

            # Badge de rentabilidade
            if _aval_val > 0 and _base_val > 0:
                _rent = (_aval_val / _base_val - 1) * 100
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
                f'<img class="card-img" src="{foto_url}" loading="lazy" onerror="this.style.display=\'none\'">'
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
        <div class="price-label">Avaliação R$</div>
        <div class="{aval_css}">{aval_disp}</div>
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
            _art_norm  = _norm_art(artista)
            _aval_val  = media_hist.get(_art_norm, 0)
            aval_str   = fmt_brl(_aval_val) if _aval_val > 0 else "sem histórico"
            aval_css   = "price-val-aval" if _aval_val > 0 else "price-val-aval-vazio"
            # % do arremate em relação à avaliação histórica
            if _aval_val > 0 and lance > 0:
                _pct = round(lance / _aval_val * 100)
                if _pct <= 80:
                    _pct_color, _pct_bg = "#7dd4a0", "#0d2e1a"
                elif _pct <= 110:
                    _pct_color, _pct_bg = "#fbbf24", "#2a1f00"
                else:
                    _pct_color, _pct_bg = "#f87171", "#2e0d0d"
                _pct_str = (
                    f'<div style="margin-top:4px;padding:3px 8px;border-radius:6px;'
                    f'background:{_pct_bg};display:inline-block">'
                    f'<span style="font-size:12px;color:{_pct_color};font-weight:700">'
                    f'{_pct}% da avaliação histórica</span></div>'
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
                f'<img class="card-img" src="{foto_url}" loading="lazy" onerror="this.style.display=\'none\'">'
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
        <div class="price-label">Avaliação R$</div>
        <div class="{aval_css}">{aval_str}</div>
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


def render_export(df, key="export"):
    cols_export = [c for c in ["artista", "titulo", "tecnica", "dimensoes", "ano", "assinatura",
                                "estimativa_min", "estimativa_max", "lance_base", "maior_lance",
                                "data_leilao", "casa", "foto_url", "url_detalhe", "data_coleta"] if c in df.columns]
    export_df = df[cols_export].copy()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Resultado")
    st.download_button(
        label="⬇️ Baixar Excel",
        data=buf.getvalue(),
        file_name="arte_resultado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key,
    )


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


def _eh_desconhecido(artista: str) -> bool:
    art = str(artista).strip()
    return not art or bool(_RE_DESCONHECIDO.search(art))


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


def render_garimpo(df_leiloes):
    """Aba de garimpo: lotes com artista desconhecido vs. índice visual histórico."""
    idx = _load_visual_index()
    tem_indice = bool(idx)

    if not tem_indice:
        st.warning(
            "Índice visual ainda não construído. "
            "Execute `python build_visual_index.py` para começar."
        )
        st.code("python build_visual_index.py --max 2000 --threads 10", language="bash")
        st.caption(f"Indexa as 2.000 obras com maior lance do histórico (~5 min). "
                   f"Pode rodar em background enquanto usa a plataforma.")
        return

    st.caption(f"Índice visual: **{len(idx):,}** obras históricas com artista identificado")

    # ── Modo teste: busca por URL de foto ──────────────────────────────────
    with st.expander("🔬 Testar com URL de foto", expanded=False):
        url_teste = st.text_input("Cole a URL de uma imagem para buscar obras similares:",
                                  placeholder="https://www.site.com.br/imagem.jpg",
                                  key="garimpo_url_teste")
        if url_teste:
            with st.spinner("Buscando similares..."):
                similares_teste = _buscar_similares(url_teste, top_n=5, max_dist=25)
            col_t1, col_t2 = st.columns([1, 2])
            with col_t1:
                st.image(url_teste, use_container_width=True)
            with col_t2:
                if not similares_teste:
                    st.info("Nenhuma obra similar encontrada no índice.")
                else:
                    _mh_t = load_media_hist()
                    st.markdown("**Obras visualmente similares:**")
                    for s in similares_teste:
                        art_norm = _norm_art(s["artista"])
                        media = _mh_t.get(art_norm, s["maior_lance"])
                        sim_color = "#7dd4a0" if s["similarity"] >= 75 else ("#fbbf24" if s["similarity"] >= 55 else "#888")
                        st.markdown(
                            f'<div style="border:1px solid #2a2a42;border-radius:8px;padding:10px;margin-bottom:8px">'
                            f'<span style="color:{sim_color};font-weight:700">{s["similarity"]}%</span> '
                            f'<b>{s["artista"]}</b><br>'
                            f'<span style="font-size:12px;color:#aaa">{s["titulo"][:60]}</span><br>'
                            f'Lance histórico: <b>{fmt_brl(s["maior_lance"])}</b> · '
                            f'Média artista: <b>{fmt_brl(media) if media else "—"}</b>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

    # Filtra lotes desconhecidos com foto
    desconhecidos = df_leiloes[
        df_leiloes["artista"].apply(_eh_desconhecido) &
        (df_leiloes["foto_url"].str.strip() != "")
    ].copy()

    total_desc = len(df_leiloes[df_leiloes["artista"].apply(_eh_desconhecido)])

    st.markdown(
        f"**{total_desc}** lotes com artista não identificado — "
        f"**{len(desconhecidos)}** com foto disponível para análise"
    )

    if desconhecidos.empty:
        st.info("Nenhum lote com artista desconhecido e foto disponível.")
        return

    # Ordena por lance_base desc (oportunidades de maior valor primeiro)
    desconhecidos = desconhecidos.sort_values("lance_base", ascending=False)

    # Limite de análise (pesado: cada lote faz 1 req HTTP)
    max_analisar = st.slider("Analisar top N lotes (por valor base)", 5, min(50, len(desconhecidos)), 10, key="garimpo_n")
    desconhecidos = desconhecidos.head(max_analisar)

    st.markdown("---")

    _mh = load_media_hist()

    for _, lote in desconhecidos.iterrows():
        foto    = lote.get("foto_url", "")
        titulo  = lote.get("titulo", "") or "Sem título"
        tecnica = lote.get("tecnica", "") or ""
        dims    = lote.get("dimensoes", "") or ""
        base    = lote.get("lance_base", 0)
        casa    = lote.get("casa", "")
        data    = lote.get("data_leilao", "")
        url     = lote.get("url_detalhe", "")

        with st.expander(f"🔍  {titulo[:60]}  —  base {fmt_brl(base)}  ·  {casa}", expanded=False):
            col_img, col_res = st.columns([1, 2])

            with col_img:
                if foto:
                    st.image(foto, use_container_width=True)
                st.caption(f"{tecnica}  {dims}".strip())
                if url:
                    st.markdown(f"[Ver lote ↗]({url})")

            with col_res:
                with st.spinner("Buscando similares no histórico..."):
                    similares = _buscar_similares(foto, top_n=5, max_dist=20)

                if not similares:
                    st.info("Nenhuma obra similar encontrada no índice visual.")
                else:
                    st.markdown("**Obras visualmente similares:**")
                    for s in similares:
                        art_norm = _norm_art(s["artista"])
                        media    = _mh.get(art_norm, s["maior_lance"])
                        sim_bar  = "█" * (s["similarity"] // 10) + "░" * (10 - s["similarity"] // 10)
                        sim_color = "#7dd4a0" if s["similarity"] >= 75 else ("#fbbf24" if s["similarity"] >= 55 else "#888")
                        st.markdown(
                            f'<div style="border:1px solid #2a2a42;border-radius:8px;padding:10px;margin-bottom:8px">'
                            f'<span style="color:{sim_color};font-weight:700">{s["similarity"]}%</span> '
                            f'<span style="font-size:11px;color:{sim_color}">{sim_bar}</span><br>'
                            f'<b>{s["artista"]}</b><br>'
                            f'<span style="font-size:12px;color:#aaa">{s["titulo"][:60]}</span><br>'
                            f'<span style="font-size:12px">{s["tecnica"]}</span><br>'
                            f'Lance histórico: <b>{fmt_brl(s["maior_lance"])}</b> · '
                            f'Média artista: <b>{fmt_brl(media) if media else "—"}</b>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    # Resumo de oportunidade
                    melhor = similares[0]
                    media_melhor = _mh.get(_norm_art(melhor["artista"]), melhor["maior_lance"])
                    if media_melhor > base > 0:
                        potencial = round((media_melhor / base - 1) * 100)
                        st.success(
                            f"💎 Potencial: lote a {fmt_brl(base)} vs média de "
                            f"**{melhor['artista']}** em {fmt_brl(media_melhor)} "
                            f"(+{potencial}% se confirmado)"
                        )


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
st.markdown("""
<div class="hero">
  <svg class="hero-bg" viewBox="0 0 1400 220" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
    <defs>
      <radialGradient id="g1" cx="20%" cy="40%" r="60%"><stop offset="0%" stop-color="#1a0a2e"/><stop offset="100%" stop-color="#06060f"/></radialGradient>
      <radialGradient id="g2" cx="80%" cy="60%" r="50%"><stop offset="0%" stop-color="#0d1a10"/><stop offset="100%" stop-color="#06060f"/></radialGradient>
      <radialGradient id="g3" cx="50%" cy="20%" r="70%"><stop offset="0%" stop-color="#1a1208"/><stop offset="100%" stop-color="#06060f"/></radialGradient>
      <filter id="blur1"><feGaussianBlur stdDeviation="18"/></filter>
      <filter id="blur2"><feGaussianBlur stdDeviation="10"/></filter>
      <filter id="blur3"><feGaussianBlur stdDeviation="6"/></filter>
    </defs>
    <rect width="1400" height="220" fill="#06060f"/>
    <!-- Fundo gradiente -->
    <ellipse cx="280" cy="110" rx="420" ry="180" fill="url(#g1)" opacity="0.9"/>
    <ellipse cx="1100" cy="90" rx="380" ry="160" fill="url(#g2)" opacity="0.8"/>
    <ellipse cx="700" cy="40" rx="500" ry="120" fill="url(#g3)" opacity="0.6"/>
    <!-- Manchas grandes — camada de base -->
    <path d="M 0 160 Q 120 60 280 130 Q 380 180 460 90 Q 540 20 650 80 Q 720 120 800 60 Q 900 0 1000 70 Q 1100 130 1200 50 Q 1320 -20 1400 90 L1400 220 L0 220Z" fill="#0b0b18" opacity="0.7"/>
    <!-- Pinceladas longas — cor quente dourada -->
    <path d="M -40 170 Q 200 90 420 150 Q 580 195 720 130 Q 860 70 1050 140 Q 1200 195 1440 110" stroke="#c9a96e" stroke-width="1.8" fill="none" opacity="0.18" filter="url(#blur2)"/>
    <path d="M -40 185 Q 180 120 350 165 Q 500 200 660 155 Q 820 108 1000 160 Q 1180 205 1440 140" stroke="#c9a96e" stroke-width="0.8" fill="none" opacity="0.09"/>
    <!-- Manchas de cor — azul profundo -->
    <path d="M 80 30 Q 160 -20 240 50 Q 300 100 200 130 Q 100 155 60 90 Z" fill="#1a3a5a" opacity="0.35" filter="url(#blur1)"/>
    <path d="M 950 10 Q 1080 -30 1150 60 Q 1200 120 1100 150 Q 990 175 960 100 Z" fill="#0f2a4a" opacity="0.4" filter="url(#blur1)"/>
    <!-- Manchas vinho / borgonha -->
    <path d="M 500 -20 Q 620 10 640 80 Q 655 140 560 160 Q 460 175 430 100 Q 410 40 500 -20 Z" fill="#3a1020" opacity="0.4" filter="url(#blur1)"/>
    <path d="M 1200 80 Q 1310 40 1380 110 Q 1420 155 1340 185 Q 1250 210 1200 160 Z" fill="#2a0e18" opacity="0.5" filter="url(#blur1)"/>
    <!-- Toque de verde escuro -->
    <path d="M 320 140 Q 400 100 480 150 Q 520 175 460 200 Q 380 215 320 185 Z" fill="#0a2a1a" opacity="0.45" filter="url(#blur1)"/>
    <path d="M 780 20 Q 860 -10 920 50 Q 950 90 890 120 Q 820 145 770 100 Z" fill="#0d2a20" opacity="0.35" filter="url(#blur1)"/>
    <!-- Pinceladas finas de detalhe — dourado -->
    <path d="M 60 200 Q 300 155 500 185 Q 650 205 780 175 Q 920 145 1100 185 Q 1260 215 1400 175" stroke="#c9a96e" stroke-width="0.6" fill="none" opacity="0.22" filter="url(#blur3)"/>
    <!-- Pontos de luz — brilho suave -->
    <circle cx="185" cy="72" r="55" fill="#2a1a4a" opacity="0.3" filter="url(#blur1)"/>
    <circle cx="185" cy="72" r="12" fill="#c9a96e" opacity="0.06" filter="url(#blur2)"/>
    <circle cx="1050" cy="55" r="70" fill="#1a2a10" opacity="0.25" filter="url(#blur1)"/>
    <circle cx="680"  cy="35" r="90" fill="#1e0e2a" opacity="0.3"  filter="url(#blur1)"/>
    <!-- Linhas de textura fina -->
    <line x1="0" y1="218" x2="1400" y2="218" stroke="#c9a96e" stroke-width="0.5" opacity="0.2"/>
  </svg>
  <div class="hero-overlay">
    <p class="hero-title">Arte em Leilão</p>
    <p class="hero-sub">Catálogo &nbsp;·&nbsp; Histórico &nbsp;·&nbsp; Análise de Mercado</p>
  </div>
</div>
""", unsafe_allow_html=True)

col_tabs, col_refresh = st.columns([10, 1])
with col_tabs:
    aba1, aba2, aba3, aba4, aba5 = st.tabs([
        "  🔨  Em Leilão Agora  ",
        "  📈  Histórico de Preços  ",
        "  📊  Análise de Mercado  ",
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

        col_r, col_d2, col_o = st.columns([2, 2, 2])
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
            _ordem_default = 0 if filtro_data == "Todas as datas" else 0
            ordem = st.selectbox(
                "Ordenar",
                ["Rentabilidade ↓", "Data ↑", "Maior Lance ↓", "Valor Base ↓", "Artista (A-Z)", "Qtd. Lances ↓"],
                key="L_ordem",
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
            lambda r: ((_mh.get(_norm_art(str(r["artista"])), 0) / r["lance_base"]) - 1) * 100
            if r["lance_base"] > 0 and _mh.get(_norm_art(str(r["artista"])), 0) > 0
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

        total_res = len(df)
        total_pag = max(1, (total_res + PER_PAGE - 1) // PER_PAGE)

        # Reset de página quando filtros mudam
        _fk = f"{fa_norm}|{ft}|{fc}|{fass}|{ffoto}|{fbase}|{preco_range}|{filtro_lance}|{filtro_data}|{ordem}"
        if st.session_state.get("L_fk") != _fk:
            st.session_state["L_fk"] = _fk
            st.session_state["L_pag"] = 1
        pag = st.session_state.get("L_pag", 1)
        pag = max(1, min(pag, total_pag))

        st.markdown(f"**{total_res}** resultado(s) — página **{pag}** de **{total_pag}**")

        if df.empty:
            st.info("Nenhum resultado.")
        else:
            df_pag = df.iloc[(pag - 1) * PER_PAGE : pag * PER_PAGE]
            render_cards_leilao(df_pag)

            # Navegação
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
            df["_aval_sort"] = df["artista"].apply(lambda a: _mh_hist.get(_norm_art(str(a)), 0))
            df = df.sort_values("_aval_sort", ascending=False)
        elif ordem == "% da Avaliação ↓":
            df = df.copy()
            def _pct_sort(r):
                av = _mh_hist.get(_norm_art(str(r["artista"])), 0)
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
