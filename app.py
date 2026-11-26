"""
TUTOR DI TRADING — app personale in stile app di trading, con il bot e la sua chat.
NON invia ordini dall'app: le operazioni le fa il bot sul conto DEMO (Capital.com) oppure le inserisci tu.

Avvio sul PC:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import urllib.request

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import backtest
import capital
import chat_bot
import coach
import eventi
import logica as L
import sentinella

# Streamlit Cloud ricarica solo questo file dopo un aggiornamento: ricarichiamo i moduli per averli sempre aggiornati
L = importlib.reload(L)
capital = importlib.reload(capital)
sentinella = importlib.reload(sentinella)
backtest = importlib.reload(backtest)
coach = importlib.reload(coach)
eventi = importlib.reload(eventi)
chat_bot = importlib.reload(chat_bot)

st.set_page_config(page_title="Tutor di Trading", page_icon="📈", layout="centered", initial_sidebar_state="collapsed")

PIANO = L.carica_piano()
MERCATI = L.mercati(PIANO)          # quelli che il bot sorveglia (base o esteso)
DEMO = os.environ.get("TUTOR_DEMO") == "1"      # solo per le prove dello sviluppatore, senza internet
URL_DATI = "https://raw.githubusercontent.com/mazzierialessandro99-wq/tutor-trading/dati/"

# ==============================================================================
# TEMA (segue il telefono) E STILE
# ==============================================================================
SCURO = (getattr(st.context.theme, "type", None) or "dark") == "dark"
if SCURO:
    T = dict(bg="#0b0d12", surf="#151821", surf2="#1d212c", bordo="#252a36", testo="#f3f4f8", testo2="#c2c6d3",
             muto="#8a90a2", acc="#4c7dff", acc2="#7a5cff", su="#21c58e", giu="#ff5c6c")
else:
    T = dict(bg="#f3f4f8", surf="#ffffff", surf2="#eef0f5", bordo="#e3e6ee", testo="#0e1117", testo2="#424857",
             muto="#6b7180", acc="#2f62f5", acc2="#6a4cf5", su="#0f9f6e", giu="#e5384b")
SEMAFORO = {"VERDE": T["su"], "GIALLO": "#f5a524", "ROSSO": T["giu"]}

st.markdown(f"<style>:root{{{';'.join(f'--{k}:{v}' for k, v in T.items())}}}</style>", unsafe_allow_html=True)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, .stApp, button, input, textarea, p, div, span, li {font-family: 'Inter', system-ui, sans-serif;}
.stApp {background: var(--bg);}
[data-testid="stHeader"], [data-testid="stDecoration"], [data-testid="stToolbar"] {display: none;}
.block-container {padding: 1rem 1rem 7rem; max-width: 560px;}
p, li {line-height: 1.5;}

/* barra di navigazione in basso, come un'app */
.st-key-navbar {position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000; background: var(--surf);
               border-top: 1px solid var(--bordo); padding: 6px 8px calc(8px + env(safe-area-inset-bottom));}
.st-key-navbar > div {max-width: 560px; margin: 0 auto;}
.st-key-navbar [data-testid="stButtonGroup"], .st-key-navbar [data-testid="stButtonGroup"] > div {width: 100%;}
.st-key-navbar button {flex: 1; border: none !important; background: transparent !important; min-height: 54px;
                      border-radius: 14px !important; padding: 2px !important; box-shadow: none !important;}
.st-key-navbar button p {font-size: .68rem !important; font-weight: 600; color: var(--muto);}
.st-key-navbar button > div > span {flex-direction: column !important; gap: 1px !important;}
.st-key-navbar button [data-testid="stIconMaterial"] {font-size: 1.5rem; color: var(--muto); margin: 0 !important;}
.st-key-navbar button[aria-checked="true"] p, .st-key-navbar button[aria-checked="true"] [data-testid="stIconMaterial"] {color: var(--acc) !important; font-weight: 700;}
.st-key-navbar button[aria-checked="true"] {background: color-mix(in srgb, var(--acc) 13%, transparent) !important;}

/* testate */
.top {display: flex; align-items: center; justify-content: space-between; margin: 2px 0 14px;}
.top-l {display: flex; align-items: center; gap: 10px;}
.top h1 {font-size: 1.5rem; font-weight: 800; margin: 0; padding: 0; color: var(--testo); letter-spacing: -.02em;}
.pill {font-size: .72rem; font-weight: 700; padding: 5px 10px; border-radius: 999px; background: var(--surf);
       border: 1px solid var(--bordo); color: var(--testo2); white-space: nowrap;}
.sez {display: flex; justify-content: space-between; align-items: baseline; margin: 22px 2px 8px;}
.sez h3 {font-size: 1.02rem; font-weight: 700; margin: 0; padding: 0; color: var(--testo);}
.sez span {font-size: .8rem; color: var(--muto);}

/* saldo grande */
.saldo-k {color: var(--muto); font-size: .85rem; font-weight: 500;}
.saldo {font-size: 2.6rem; font-weight: 800; letter-spacing: -.03em; color: var(--testo); line-height: 1.1; margin: 2px 0;}
.saldo small {font-size: 1.4rem; color: var(--muto); font-weight: 700;}
.var {font-weight: 700; font-size: .92rem;}

/* schede e righe */
.card {background: var(--surf); border: 1px solid var(--bordo); border-radius: 20px; padding: 14px 16px; margin: 8px 0;}
.card .t {font-weight: 700; color: var(--testo); margin-bottom: 2px;}
.txt {color: var(--testo2); font-size: .92rem; line-height: 1.5;}
.txt b {color: var(--testo);}
.nota {color: var(--muto); font-size: .8rem; line-height: 1.45;}
.lista-card {background: var(--surf); border: 1px solid var(--bordo); border-radius: 20px; padding: 2px 14px; margin: 8px 0;}
.riga {display: flex; align-items: center; gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--bordo);}
.lista-card .riga:last-child {border-bottom: none;}
.logo {flex: 0 0 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
       font-weight: 800; font-size: .8rem; color: #fff; position: relative;}
.logo i {position: absolute; right: -1px; bottom: -1px; width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--surf);}
.r-c {flex: 1; min-width: 0;}
.r-t {font-weight: 600; color: var(--testo); font-size: .95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.r-s {color: var(--muto); font-size: .78rem; margin-top: 1px;}
.r-d {text-align: right; flex: 0 0 auto;}
.r-p {font-weight: 600; color: var(--testo); font-size: .92rem;}
.r-v {font-size: .78rem; font-weight: 600;}

/* righe toccabili: un pulsante invisibile sopra la riga */
.st-key-lista_mercati {background: var(--surf); border: 1px solid var(--bordo); border-radius: 20px; padding: 2px 14px; gap: 0 !important;}
[class*="st-key-tap_"] {position: relative; gap: 0 !important;}
[class*="st-key-tap_"] + [class*="st-key-tap_"] {border-top: 1px solid var(--bordo);}
[class*="st-key-tap_"] .riga {border-bottom: none;}
[class*="st-key-tap_"] [data-testid="stMarkdownContainer"], [class*="st-key-tap_"] [data-testid="stMarkdown"] {margin-bottom: 0 !important;}
[class*="st-key-tap_"] [class*="st-key-btn_"] {position: absolute !important; inset: 0; z-index: 3;}
[class*="st-key-tap_"] [class*="st-key-btn_"] * {width: 100% !important; height: 100% !important;}
[class*="st-key-tap_"] [class*="st-key-btn_"] button {opacity: 0;}

/* azioni rapide */
.st-key-azioni {gap: 8px !important; margin-top: 6px;}
.st-key-azioni [data-testid="stButton"] button {flex-direction: column; height: 76px; border-radius: 20px;
     background: var(--surf); border: 1px solid var(--bordo); color: var(--testo);}
.st-key-azioni button p {font-size: .74rem !important; font-weight: 600;}
.st-key-azioni button [data-testid="stIconMaterial"] {font-size: 1.55rem; color: var(--acc); margin: 0 0 2px !important;}
.stButton button {border-radius: 14px; font-weight: 600;}
.st-key-indietro button {border: none; background: transparent; padding: 0; min-height: 0; color: var(--acc);}

/* robot e chat */
.robot {animation: galleggia 3.4s ease-in-out infinite; flex: 0 0 auto;}
.robot .occhi {transform-origin: 50px 45px; animation: battito 5s infinite;}
.robot .luce {animation: respira 2.2s ease-in-out infinite;}
@keyframes battito {0%, 92%, 100% {transform: scaleY(1);} 95% {transform: scaleY(.1);}}
@keyframes respira {0%, 100% {opacity: .9;} 50% {opacity: .35;}}
@keyframes galleggia {0%, 100% {transform: translateY(0);} 50% {transform: translateY(-2px);}}
.bot-card {display: flex; gap: 12px; align-items: center; background: linear-gradient(135deg,
           color-mix(in srgb, var(--acc) 22%, var(--surf)), color-mix(in srgb, var(--acc2) 16%, var(--surf)));
           border: 1px solid var(--bordo); border-radius: 22px; padding: 14px; margin: 14px 0 8px;}
.bot-card .n {font-weight: 700; color: var(--testo); display: flex; align-items: center; gap: 6px;}
.dot {width: 8px; height: 8px; border-radius: 50%; display: inline-block; animation: respira 1.6s infinite;}
.msg {display: flex; gap: 8px; margin: 10px 0; align-items: flex-end;}
.msg.io {justify-content: flex-end;}
.bub {max-width: 84%; padding: 10px 14px; border-radius: 20px; font-size: .93rem; line-height: 1.5;}
.msg.bot .bub {background: var(--surf); border: 1px solid var(--bordo); color: var(--testo2); border-bottom-left-radius: 6px;}
.msg.bot .bub b {color: var(--testo);}
.msg.io .bub {background: var(--acc); color: #fff; border-bottom-right-radius: 6px;}
.chat-hero {text-align: center; margin: 4px 0 6px;}
.chat-hero .robot {animation-duration: 4s;}
[data-testid="stChatInput"] {border-radius: 18px;}
.bub.nuovo {position: relative;}
.bub.nuovo .tx {animation: appari .35s 1.1s both;}
.bub.nuovo .puntini {position: absolute; left: 14px; top: 12px; display: flex; gap: 4px; animation: sparisci .2s 1.1s both;}
.puntini i {width: 7px; height: 7px; border-radius: 50%; background: var(--muto); animation: salta 1s infinite;}
.puntini i:nth-child(2) {animation-delay: .15s;} .puntini i:nth-child(3) {animation-delay: .3s;}
@keyframes salta {0%, 60%, 100% {transform: translateY(0); opacity: .5;} 30% {transform: translateY(-4px); opacity: 1;}}
@keyframes appari {from {opacity: 0;} to {opacity: 1;}}
@keyframes sparisci {from {opacity: 1;} to {opacity: 0; visibility: hidden;}}
.avviso {display: flex; gap: 12px; align-items: center; border-radius: 18px; padding: 12px 14px; margin: 10px 0 4px;
         background: var(--surf); border: 1px solid var(--bordo); border-left: 4px solid var(--c);}
.avviso .ic {font-size: 1.3rem;}

/* semaforo e tutor */
.sem {display: flex; align-items: center; gap: 12px; padding: 13px 15px; border-radius: 20px; margin: 10px 0 8px;
      background: var(--surf); border: 1px solid var(--bordo);}
.sem b {font-size: 1rem;}
.chips {display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 6px;}
.chip {padding: 6px 11px; border-radius: 999px; font-weight: 600; font-size: .8rem; background: var(--surf); border: 1px solid var(--bordo); color: var(--testo);}
.ul {margin: 4px 0 0; padding: 0; list-style: none;}
.ul li {padding: 5px 0 5px 24px; position: relative; color: var(--testo2); font-size: .9rem;}
.ul li b {color: var(--testo);}
.ul li::before {position: absolute; left: 2px; top: 5px; font-weight: 800;}
.ul.si li::before {content: "✓"; color: var(--su);}
.ul.no li::before {content: "✕"; color: var(--giu);}
.stop {border-radius: 16px; padding: 11px 13px; margin: 6px 0; border: 1px solid var(--bordo); background: var(--surf);}
.stop.on {border: 1.5px solid var(--acc); background: color-mix(in srgb, var(--acc) 7%, var(--surf));}
.stop .a {display: flex; justify-content: space-between; font-weight: 700; color: var(--testo);}
.stop .b {font-size: .78rem; color: var(--muto); margin: 3px 0;}
.tag {font-size: .62rem; font-weight: 800; padding: 2px 7px; border-radius: 999px; background: var(--acc); color: #fff; margin-left: 6px; vertical-align: 2px;}
.warn {color: var(--giu); font-size: .82rem; font-weight: 600; margin-top: 3px;}
.griglia2 {display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 8px 0;}
.mini {background: var(--surf); border: 1px solid var(--bordo); border-radius: 18px; padding: 12px 14px;}
.mini .k {color: var(--muto); font-size: .75rem; font-weight: 500;}
.mini .v {font-size: 1.2rem; font-weight: 800; color: var(--testo); margin-top: 2px;}
.mini .s {color: var(--muto); font-size: .72rem;}
.passo {display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--bordo);}
.passo:last-child {border-bottom: none;}
.num {flex: 0 0 26px; height: 26px; border-radius: 50%; background: color-mix(in srgb, var(--acc) 15%, transparent);
      color: var(--acc); font-weight: 800; font-size: .8rem; display: flex; align-items: center; justify-content: center;}
[data-testid="stExpander"] details {border-radius: 18px; background: var(--surf); border-color: var(--bordo);}
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# IL ROBOT (disegno originale: testa liscia, visiera scura, occhi luminosi)
# ==============================================================================
def robot(dim: int = 44, occhi: str = "#5ad1ff") -> str:
    return f"""<svg class="robot" width="{dim}" height="{dim}" viewBox="0 0 100 100" aria-hidden="true">
<defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c3cad7"/></linearGradient>
<radialGradient id="rv" cx=".5" cy=".35" r=".75"><stop offset="0" stop-color="#22304a"/><stop offset="1" stop-color="#06080d"/></radialGradient></defs>
<rect x="39" y="82" width="22" height="12" rx="5" fill="#a5aebe"/>
<path d="M50 7 C77 7 87 26 87 46 C87 70 70 86 50 86 C30 86 13 70 13 46 C13 26 23 7 50 7 Z" fill="url(#rg)" stroke="#97a1b2" stroke-width="1.5"/>
<path d="M50 10 C40 10 33 13 29 18" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" opacity=".9"/>
<path d="M23 38 C23 28 34 24 50 24 C66 24 77 28 77 38 L77 52 C77 60 66 64 50 64 C34 64 23 60 23 52 Z" fill="url(#rv)"/>
<ellipse class="luce" cx="38" cy="45" rx="11" ry="8" fill="{occhi}" opacity=".28"/><ellipse class="luce" cx="62" cy="45" rx="11" ry="8" fill="{occhi}" opacity=".28"/>
<g class="occhi"><ellipse cx="38" cy="45" rx="6" ry="4.5" fill="{occhi}"/><ellipse cx="62" cy="45" rx="6" ry="4.5" fill="{occhi}"/>
<circle cx="36" cy="43.5" r="1.4" fill="#fff"/><circle cx="60" cy="43.5" r="1.4" fill="#fff"/></g>
<path d="M41 74 Q50 78 59 74" stroke="#8a94a6" stroke-width="2.4" fill="none" stroke-linecap="round"/>
<circle cx="15" cy="48" r="4" fill="#d6dce6" stroke="#97a1b2"/><circle cx="85" cy="48" r="4" fill="#d6dce6" stroke="#97a1b2"/>
</svg>"""


# ==============================================================================
# FORMATI
# ==============================================================================
def num(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def prezzo(p: float) -> str:
    return num(p, 4 if abs(p) < 10 else 2)


def quote(q: float) -> str:
    return num(q, 0 if q >= 100 else 2 if q >= 1 else 4)


def pct(x: float) -> str:
    return num(x, 2).rstrip("0").rstrip(",")


def euro_s(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}{num(abs(x))} €"


# ==============================================================================
# DATI
# ==============================================================================
def _dati_demo(ticker: str) -> pd.DataFrame:
    rng = np.random.default_rng(sum(map(ord, ticker)))
    n = 1300
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0007, 0.012, n)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + rng.uniform(0, .008, n))
    lo = np.minimum(op, close) * (1 - rng.uniform(0, .008, n))
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close}, index=idx)


@st.cache_data(ttl=1800, show_spinner=False)
def tutti_i_dati() -> dict:
    tickers = [t for t, _ in MERCATI.values()]
    if DEMO:
        return {t: _dati_demo(t) for t in tickers}
    try:
        return sentinella.scarica_tutti(tickers, periodo="5y")
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _scarica_singolo(ticker: str) -> pd.DataFrame:
    if DEMO:
        return _dati_demo(ticker)
    try:
        return sentinella.scarica_tutti([ticker], periodo="5y").get(ticker, pd.DataFrame())
    except Exception:
        return pd.DataFrame()


def dati_di(ticker: str) -> pd.DataFrame:
    d = tutti_i_dati().get(ticker)
    return d if d is not None else _scarica_singolo(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def cambio_eur(valuta: str) -> float:
    if valuta == "EUR":
        return 1.0
    if DEMO:
        return 1.08
    d = _scarica_singolo(f"EUR{valuta}=X")
    return float(d["Close"].iloc[-1]) if len(d) else 1.0


def prepara(d: pd.DataFrame) -> pd.DataFrame:
    return backtest.segnali_mercato(d).iloc[L.EMA_PERIODO:]


def categoria(ticker: str) -> str:
    if L.is_cripto(ticker):
        return "Cripto"
    if ticker.endswith("=X"):
        return "Valute"
    if ticker.endswith("=F"):
        return "Materie prime"
    if ticker.startswith("^") or ticker == "FTSEMIB.MI":
        return "Indici"
    return "Azioni"


@st.cache_data(ttl=1800, show_spinner=False)
def panoramica() -> list[dict]:
    righe = []
    for nome, (ticker, valuta) in MERCATI.items():
        d = tutti_i_dati().get(ticker)
        if d is None or len(d) < L.EMA_PERIODO + 20:
            continue
        v = L.valuta(L.aggiungi_indicatori(d))
        righe.append({"nome": nome, "ticker": ticker, "valuta": valuta, "colore": v["colore"], "close": v["close"],
                      "var": (d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1) * 100, "cat": categoria(ticker),
                      "spark": d["Close"].iloc[-60:].tolist(), "rsi": v["rsi"]})
    return righe


@st.cache_data(ttl=120, show_spinner=False)
def memoria(nome_file: str = "stato_sentinella.json") -> dict | None:
    locale = os.environ.get("MEMORIA_BOT_DIR")
    try:
        if locale:
            with open(os.path.join(locale, nome_file), encoding="utf-8") as f:
                return json.load(f)
        with urllib.request.urlopen(URL_DATI + nome_file, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def notizie_di(ticker: str) -> list[dict]:
    if DEMO:
        return [{"titolo": f"Titolo di prova {i} su {ticker}", "fonte": "Prova", "link": "", "data": pd.Timestamp.now() - pd.Timedelta(hours=3 * i)}
                for i in range(1, 4)]
    return eventi.notizie(ticker)


def html_notizie(lista: list[dict]) -> str:
    righe = ""
    for n in lista:
        quando = f"{pd.Timestamp(n['data']):%d/%m %H:%M}" if n.get("data") is not None else ""
        titolo = n["titolo"].replace("<", "&lt;")
        titolo = f'<a href="{n["link"]}" target="_blank" style="color:var(--testo);text-decoration:none">{titolo}</a>' if n.get("link") else titolo
        righe += (f'<div class="riga"><div class="r-c"><div class="r-t" style="white-space:normal;font-size:.9rem">{titolo}</div>'
                  f'<div class="r-s">{n.get("fonte", "")} · {quando}</div></div></div>')
    return f'<div class="lista-card">{righe}</div>'


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def calcola_backtest(capitale: float) -> dict:
    tickers = [t for t, _ in MERCATI.values()]
    dati = {t: _dati_demo(t) for t in tickers} if DEMO else sentinella.scarica_tutti(tickers, periodo="5y")
    r = backtest.esegui(dati, capitale, PIANO)
    r["mercati"] = len(dati)
    return r


# ==============================================================================
# STATO DELL'APP E NAVIGAZIONE
# ==============================================================================
ss = st.session_state
ss.setdefault("capitale", float(PIANO.get("capitale", 1000)))
ss.setdefault("rischio", float(PIANO.get("rischio_per_operazione", 1.0)))
ss.setdefault("aperto", None)
ss.setdefault("chat", [])
ss.setdefault("pagina", "home")
PAGINE = {"home": ":material/home: Home", "mercati": ":material/candlestick_chart: Mercati",
          "chat": ":material/smart_toy: Bot", "impara": ":material/school: Impara", "altro": ":material/tune: Altro"}


def vai(pagina: str, mercato: tuple | None = None):
    ss.pagina = ss.barra = pagina
    if mercato is not None:
        ss.aperto = mercato


def da_barra():
    ss.pagina = ss.barra
    if ss.barra == "mercati":
        ss.aperto = None


# ==============================================================================
# PEZZI GRAFICI
# ==============================================================================
COLORI_LOGO = ["#4c7dff", "#7a5cff", "#18b47b", "#e8961c", "#ec5b8d", "#14a7bb", "#f07a32", "#6f9c2f"]


def logo(nome: str, colore_sem: str | None = None) -> str:
    iniz = "".join(w[0] for w in re.sub(r"[^A-Za-z0-9 ]", " ", nome).split()[:2]).upper() or "?"
    c = COLORI_LOGO[int(hashlib.md5(nome.encode()).hexdigest(), 16) % len(COLORI_LOGO)]
    pallino = f'<i style="background:{colore_sem}"></i>' if colore_sem else ""
    return f'<div class="logo" style="background:{c}">{iniz[:2]}{pallino}</div>'


def spark(valori: list[float], w: int = 58, h: int = 26) -> str:
    v = np.array(valori, dtype=float)
    y = h - 2 - (v - v.min()) / ((v.max() - v.min()) or 1) * (h - 4)
    x = np.linspace(1, w - 1, len(v))
    col = T["su"] if v[-1] >= v[0] else T["giu"]
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, y))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="flex:0 0 auto"><polyline points="{pts}" '
            f'fill="none" stroke="{col}" stroke-width="1.8" stroke-linejoin="round"/></svg>')


def grafico_linea(serie: pd.Series, altezza: int = 220, base: float | None = None) -> go.Figure:
    col = T["su"] if serie.iloc[-1] >= (base if base is not None else serie.iloc[0]) else T["giu"]
    fig = go.Figure(go.Scatter(x=serie.index, y=serie.values, mode="lines", line=dict(color=col, width=2.4),
                               fill="tozeroy", fillcolor=col + ("26" if SCURO else "1c"), hovertemplate="%{y:,.2f}<extra></extra>"))
    lo, hi = float(serie.min()), float(serie.max())
    if base is not None:
        fig.add_hline(y=base, line=dict(color=T["muto"], width=1, dash="dot"))
        lo, hi = min(lo, base), max(hi, base)
    pad = max((hi - lo) * .15, abs(hi) * .002)
    fig.update_layout(height=altezza, margin=dict(l=0, r=0, t=4, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", showlegend=False, hovermode="x unified", separators=",.",
                      font=dict(color=T["muto"], size=11), dragmode=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, range=[lo - pad, hi + pad])
    return fig


def testata(titolo: str, destra: str = ""):
    st.markdown(f'<div class="top"><div class="top-l"><h1>{titolo}</h1></div>{destra}</div>', unsafe_allow_html=True)


def sezione(titolo: str, destra: str = ""):
    st.markdown(f'<div class="sez"><h3>{titolo}</h3><span>{destra}</span></div>', unsafe_allow_html=True)


def card(html: str):
    st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)


def occhi_bot(m: dict | None, ric: dict | None) -> str:
    """Occhi verdi se il bot è in guadagno, rossi se in perdita, gialli se fermo o in pausa, azzurri all'inizio."""
    etichetta, col, _ = stato_bot(m, ric)
    if col != SEMAFORO["VERDE"]:
        return "#f5c542" if col == SEMAFORO["GIALLO"] else "#ff6b6b"
    storia = (m or {}).get("storia") or []
    cap0 = float((m or {}).get("capitale_piano") or PIANO.get("capitale", 0))
    diff = float(storia[-1][1]) - cap0 if storia else 0
    return "#3ee39a" if diff > 0.5 else "#ff6b6b" if diff < -0.5 else "#5ad1ff"


def stato_bot(m: dict | None, ric: dict | None) -> tuple[str, str, str]:
    """(etichetta, colore, frase) dello stato del bot."""
    if not m:
        return "In avvio", SEMAFORO["GIALLO"], "Sto preparando la mia memoria: torno tra poco."
    try:
        ultimo = pd.Timestamp(m["ultimo_giro"])
        ultimo = ultimo.tz_localize("Europe/Rome") if ultimo.tzinfo is None else ultimo
        fermo = (pd.Timestamp.now(tz="Europe/Rome") - ultimo).total_seconds() > 75 * 60
    except Exception:
        fermo = True
    if fermo:
        return "Fermo?", SEMAFORO["ROSSO"], "Non do notizie da più di un'ora: il motore potrebbe essersi fermato."
    if m.get("modalita") == "pausa":
        return "In pausa", SEMAFORO["GIALLO"], "Sono in pausa: guardo i mercati ma non apro operazioni. Scrivi /riprendi su Telegram."
    vinc = (ric or {}).get("vincitrice")
    if m.get("modalita") == "automatica" and vinc:
        return "Opero sul Demo", SEMAFORO["VERDE"], "Opero con la regola promossa dalla ricerca della settimana."
    if m.get("modalita") == "automatica" and PIANO.get("palestra"):
        return "Palestra sul Demo", SEMAFORO["VERDE"], ("Opero sul Demo la strategia di base: ogni operazione è un esperimento "
                                                         "per studiare il mercato dal vivo.")
    if m.get("modalita") == "automatica":
        return "Osservo", SEMAFORO["GIALLO"], "Guardo i mercati senza operare: la ricerca non trova un vantaggio affidabile."
    return "Solo avvisi", SEMAFORO["GIALLO"], "Ti mando gli avvisi su Telegram: gli ordini li metti tu."


# ==============================================================================
# HOME
# ==============================================================================
def schermata_home():
    m, ric = memoria(), memoria("ricerca_esito.json")
    etichetta, col, frase = stato_bot(m, ric)
    occhi = occhi_bot(m, ric)
    st.markdown(f'<div class="top"><div class="top-l">{robot(40, occhi)}<h1>Ciao!</h1></div><span class="pill">● Conto Demo</span></div>',
                unsafe_allow_html=True)
    cap0 = float((m or {}).get("capitale_piano") or PIANO.get("capitale", 0))
    # solo i punti del piano attuale (prima c'era il vecchio piano da 500 €)
    storia = [x for x in (m or {}).get("storia") or [] if not cap0 or abs(float(x[1]) - cap0) < cap0 * .5]
    attuale = float(storia[-1][1]) if storia else cap0
    diff = attuale - cap0
    # saldo vero del conto Demo = saldo all'avvio del piano + quello che ha fatto il bot da allora
    base = ((m or {}).get("obiettivo_traccia") or {}).get("base")
    reale = float(base) + diff if base else attuale
    intero, dec = num(reale).split(",")
    st.markdown(f'<div class="saldo-k">Conto Demo Capital.com</div>'
                f'<div class="saldo">{intero}<small>,{dec} €</small></div>'
                f'<div class="var" style="color:{T["su"] if diff >= 0 else T["giu"]}">{"▲" if diff >= 0 else "▼"} '
                f'{num(abs(diff))} € fatti dal bot · {num(abs(diff) / cap0 * 100 if cap0 else 0)}%</div>'
                + (f'<div class="nota" style="margin-top:2px">Il bot conta da {num(float(base))} €: le operazioni fatte a mano prima '
                   f'non sono sue.</div>' if base else ""), unsafe_allow_html=True)
    valori = [float(x[1]) for x in storia]
    if len(storia) >= 2 and max(valori) - min(valori) > max(cap0 * .001, 1):     # solo se si è mosso davvero
        s = pd.Series([float(x[1]) for x in storia], index=pd.to_datetime([x[0] for x in storia], utc=True))
        st.plotly_chart(grafico_linea(s, 160, base=cap0), width="stretch", config={"displayModeBar": False, "staticPlot": True})

    if (m or {}).get("tensione"):
        st.markdown(f'<div class="avviso" style="--c:{T["giu"]}"><span class="ic">🌩️</span><div class="r-c"><div class="r-t">Mercati in tensione</div>'
                    f'<div class="r-s" style="white-space:normal">L\'indice della paura (VIX) è a {num(float(m.get("vix") or 0), 1)}: '
                    f'il bot rischia la metà su ogni nuova operazione.</div></div></div>', unsafe_allow_html=True)

    # notifica: l'ultima operazione aperta o chiusa nelle ultime 48 ore
    for d in reversed((m or {}).get("decisioni") or []):
        if not d["decisione"].startswith("Operazione "):
            continue
        quando = pd.Timestamp(d["ora"])
        quando = quando.tz_localize("Europe/Rome") if quando.tzinfo is None else quando
        if (pd.Timestamp.now(tz="Europe/Rome") - quando).total_seconds() < 48 * 3600:
            c = T["giu"] if d.get("icona") == "❌" else T["su"] if d.get("icona") == "✅" else T["acc"]
            st.markdown(f'<div class="avviso" style="--c:{c}"><span class="ic">{d.get("icona", "🔔")}</span><div class="r-c">'
                        f'<div class="r-t">{d["mercato"]} · {d["decisione"].lower()}</div><div class="r-s" style="white-space:normal">'
                        f'{d["motivo"]} · {quando:%d/%m %H:%M}</div></div></div>', unsafe_allow_html=True)
        break

    with st.container(key="azioni", horizontal=True):
        st.button("Chiedi", icon=":material/forum:", on_click=vai, args=("chat",), width="stretch")
        st.button("Mercati", icon=":material/candlestick_chart:", on_click=vai, args=("mercati",), width="stretch")
        st.button("Piano", icon=":material/flag:", on_click=vai, args=("altro",), width="stretch")
        st.button("Impara", icon=":material/school:", on_click=vai, args=("impara",), width="stretch")

    st.markdown(f'<div class="bot-card">{robot(52, occhi)}<div style="flex:1;min-width:0"><div class="n">Sentinella '
                f'<span class="dot" style="background:{col}"></span><span class="nota">{etichetta}</span></div>'
                f'<div class="txt" style="margin-top:3px">{frase}</div></div></div>', unsafe_allow_html=True)
    st.button("Parla con il bot", icon=":material/chat_bubble:", on_click=vai, args=("chat",), width="stretch", type="primary")

    ob = float((m or {}).get("obiettivo") or PIANO.get("obiettivo", 0) or 0)
    if ob > cap0:
        q = max(0.0, min(1.0, (attuale - cap0) / (ob - cap0)))
        card(f'<div style="display:flex;justify-content:space-between"><span class="t">Obiettivo +{(ob / cap0 - 1) * 100:.0f}%</span>'
             f'<span class="nota">{num(ob, 0)} €</span></div>'
             f'<div style="height:8px;border-radius:99px;background:var(--surf2);margin:10px 0 6px;overflow:hidden">'
             f'<div style="width:{max(q * 100, 2):.1f}%;height:100%;background:linear-gradient(90deg,var(--acc),var(--acc2))"></div></div>'
             f'<div class="nota">{q * 100:.0f}% del percorso · Palestra sul conto Demo</div>')

    pos = (m or {}).get("posizioni") or []
    sezione("Operazioni aperte", str(len(pos)))
    if not pos:
        card('<div class="txt">Nessuna operazione aperta. Il bot entra quando un semaforo diventa verde.</div>')
    else:
        righe = ""
        for p in pos:
            upl = float(p.get("upl") or 0)
            righe += (f'<div class="riga">{logo(p.get("nome") or "")}<div class="r-c"><div class="r-t">{p.get("nome")}</div>'
                      f'<div class="r-s">{quote(float(p.get("size") or 0))} a {prezzo(float(p.get("livello") or 0))} · '
                      f'stop {prezzo(float(p.get("stop") or 0))}</div></div>'
                      f'<div class="r-d"><div class="r-p" style="color:{T["su"] if upl >= 0 else T["giu"]}">{euro_s(upl)}</div>'
                      f'<div class="r-s">tp {prezzo(float(p.get("tp") or 0))}</div></div></div>')
        st.markdown(f'<div class="lista-card">{righe}</div>', unsafe_allow_html=True)

    decisioni = list(reversed((m or {}).get("decisioni") or []))[:8]
    sezione("Attività", "le decisioni del bot")
    if not decisioni:
        card('<div class="txt">Qui vedrai ogni decisione del bot: segnali visti, operazioni aperte o saltate, e il motivo.</div>')
    else:
        righe = ""
        for d in decisioni:
            t = pd.Timestamp(d["ora"])
            righe += (f'<div class="riga"><div class="logo" style="background:var(--surf2);color:var(--testo);font-size:1rem">'
                      f'{d.get("icona", "•")}</div><div class="r-c"><div class="r-t">{d["mercato"]}</div>'
                      f'<div class="r-s" style="white-space:normal">{d["decisione"]} · {d["motivo"]}</div></div>'
                      f'<div class="r-d"><div class="r-s">{t:%d/%m}</div><div class="r-s">{t:%H:%M}</div></div></div>')
        st.markdown(f'<div class="lista-card">{righe}</div>', unsafe_allow_html=True)


# ==============================================================================
# MERCATI
# ==============================================================================
def schermata_mercati():
    if ss.aperto:
        return dettaglio_mercato(*ss.aperto)
    testata("Mercati", '<span class="pill">giornaliero</span>')
    with st.spinner("Carico i mercati…"):
        righe = panoramica()
    if not righe:
        st.error("Non riesco a scaricare i prezzi in questo momento. Riprova tra qualche minuto.")
        return
    with st.form("cerca", border=False):
        sim = st.text_input("Cerca un altro simbolo", placeholder="Cerca un simbolo: ENI.MI, TSLA, ETH-USD…", label_visibility="collapsed")
        if st.form_submit_button("Analizza", icon=":material/search:", width="stretch") and sim.strip():
            ss.aperto = (sim.strip().upper(), sim.strip().upper())
            st.rerun()
    n = {c: sum(r["colore"] == c for r in righe) for c in SEMAFORO}
    st.markdown('<div class="griglia2" style="grid-template-columns:repeat(3,1fr)">' + "".join(
        f'<div class="mini"><div class="k">{lab}</div><div class="v" style="color:{SEMAFORO[c]}">{n[c]}</div></div>'
        for c, lab in (("VERDE", "🟢 Verdi"), ("GIALLO", "🟡 Gialli"), ("ROSSO", "🔴 Rossi"))) + "</div>", unsafe_allow_html=True)
    filtro = st.pills("Categoria", ["Tutti", "Indici", "Azioni", "Materie prime", "Valute", "Cripto"], default="Tutti",
                      key="cat", label_visibility="collapsed") or "Tutti"
    ordine = {"VERDE": 0, "GIALLO": 1, "ROSSO": 2}
    vis = sorted([r for r in righe if filtro == "Tutti" or r["cat"] == filtro], key=lambda r: (ordine[r["colore"]], r["nome"]))
    with st.container(key="lista_mercati"):
        for r in vis:
            k = re.sub(r"[^A-Za-z0-9]", "", r["ticker"])
            with st.container(key=f"tap_{k}"):
                su = r["var"] >= 0
                st.markdown(f'<div class="riga">{logo(r["nome"], SEMAFORO[r["colore"]])}<div class="r-c"><div class="r-t">{r["nome"]}</div>'
                            f'<div class="r-s">{r["cat"]} · RSI {r["rsi"]:.0f}</div></div>{spark(r["spark"])}'
                            f'<div class="r-d"><div class="r-p">{prezzo(r["close"])}</div>'
                            f'<div class="r-v" style="color:{T["su"] if su else T["giu"]}">{"+" if su else "−"}{num(abs(r["var"]))}%</div></div></div>',
                            unsafe_allow_html=True)
                st.button(r["nome"], key=f"btn_{k}", on_click=vai, args=("mercati", (r["nome"], r["ticker"])))


def dettaglio_mercato(nome: str, ticker: str):
    st.button("‹ Mercati", key="indietro", on_click=lambda: ss.update(aperto=None))
    d = dati_di(ticker)
    if d is None or len(d) < L.EMA_PERIODO + 50:
        st.error(f"Non trovo abbastanza dati per {ticker}.")
        return
    df = prepara(d)
    v = L.valuta(df)
    valuta = MERCATI.get(nome, (None, "USD"))[1] or "USD"
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta + " ")
    var = (df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100
    st.markdown(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0 10px">{logo(nome, SEMAFORO[v["colore"]])}'
                f'<div><div class="r-t" style="font-size:1.1rem">{nome}</div><div class="r-s">{L.nome_capital(ticker, nome)} su Capital.com</div></div></div>'
                f'<div class="saldo" style="font-size:2.2rem">{sim}{prezzo(v["close"])}</div>'
                f'<div class="var" style="color:{T["su"] if var >= 0 else T["giu"]}">{"▲" if var >= 0 else "▼"} {num(abs(var))}% oggi</div>',
                unsafe_allow_html=True)
    periodo = st.segmented_control("Periodo", ["1M", "3M", "6M", "1A", "3A"], default="6M", required=True, key=f"per_{ticker}",
                                   label_visibility="collapsed", width="stretch")
    giorni = {"1M": 31, "3M": 92, "6M": 183, "1A": 365, "3A": 1095}[periodo]
    serie = df["Close"][df.index >= df.index[-1] - pd.Timedelta(days=giorni)]
    fig = grafico_linea(serie, 230)
    ema = df["EMA200"][serie.index]
    fig.add_trace(go.Scatter(x=ema.index, y=ema.values, mode="lines", line=dict(color=T["acc"], width=1.4, dash="dot"),
                             hovertemplate="EMA 200 %{y:,.2f}<extra></extra>"))
    lo, hi = float(min(serie.min(), ema.min())), float(max(serie.max(), ema.max()))
    fig.update_yaxes(range=[lo - (hi - lo) * .1, hi + (hi - lo) * .1])
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.button(f"Chiedi al bot di {nome}", icon=":material/smart_toy:", width="stretch", key="chiedi_mercato",
              on_click=lambda: (ss.update(domanda=f"Analizza {nome}"), vai("chat")))
    st.markdown('<div class="nota">Linea blu tratteggiata: la EMA 200, la direzione di fondo.</div>', unsafe_allow_html=True)

    col = SEMAFORO[v["colore"]]
    st.markdown(f'<div class="sem" style="border-color:{col}"><span class="dot" style="background:{col};width:14px;height:14px;flex:0 0 14px"></span>'
                f'<div><b style="color:{col}">Semaforo {v["colore"].lower()}</b><div class="txt">{v["sintesi"]}</div></div></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="griglia2">' + "".join(
        f'<div class="mini"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
        for k, val, s in [("RSI", f"{v['rsi']:.0f}", "il momento"), ("ATR", num(v["atr"], 4 if v["close"] < 10 else 2), "movimento al giorno"),
                          ("EMA 200", prezzo(v["ema"]), "il trend"), ("Dalla EMA", f"{(v['close'] / v['ema'] - 1) * 100:+.1f}%".replace(".", ","), "distanza")])
                + "</div>", unsafe_allow_html=True)

    lista = notizie_di(ticker)
    ev = eventi.evento_vicino(ticker, pd.Timestamp.now().date())
    if ev:
        st.markdown(f'<div class="avviso" style="--c:#f5a524"><span class="ic">📅</span><div class="txt">'
                    f'<b>Evento in arrivo</b>: {ev}. Il bot qui non apre nuove operazioni.</div></div>', unsafe_allow_html=True)
    if lista:
        sezione("Notizie", "per informarti, non decidono le operazioni")
        st.markdown(html_notizie(lista), unsafe_allow_html=True)

    s = coach.analizza(df)
    ric_ok = bool((memoria("ricerca_esito.json") or {}).get("vincitrice"))
    sezione("Il tutor", "cosa fare oggi")
    st.markdown('<div class="chips">' + "".join(f'<span class="chip">{coach.ETICHETTE[k][s[k]][0]} {coach.ETICHETTE[k][s[k]][1]}</span>'
                                                for k in ("trend", "momento", "vol")) + "</div>", unsafe_allow_html=True)
    fare, non = coach.consigli(s, ric_ok)
    card('<div class="t">Cosa fare</div><ul class="ul si">' + "".join(f"<li>{x}</li>" for x in fare) + "</ul>")
    card('<div class="t">Cosa non fare</div><ul class="ul no">' + "".join(f"<li>{x}</li>" for x in non) + "</ul>")

    cambio = cambio_eur(valuta)
    rischio = L.rischio_per(ticker, PIANO, ss.rischio)
    metodi = [x for x in coach.metodi_stop(s, ss.capitale * cambio, rischio) if x["distanza"] > 0]
    cons = next((x for x in metodi if x["consigliato"]), metodi[0])
    sezione("Dove mettere lo stop loss")
    brevi = {"atr": "Volatilità", "struttura": "Minimo recente", "percentuale": "Percentuale"}
    scelta = st.segmented_control("Stop", [x["chiave"] for x in metodi], default=cons["chiave"], required=True,
                                  format_func=lambda k: brevi.get(k, k), key=f"stop_{ticker}", label_visibility="collapsed", width="stretch")
    scelto = next(x for x in metodi if x["chiave"] == scelta)
    dec = 4 if s["close"] < 10 else 2
    for x in metodi:
        st.markdown(f'<div class="stop{" on" if x is scelto else ""}"><div class="a"><span>{x["nome"]}'
                    f'{"<span class=tag>CONSIGLIATO</span>" if x["consigliato"] else ""}</span><span>{sim}{prezzo(x["stop"])}</span></div>'
                    f'<div class="b">distanza {num(x["distanza"], dec)} ({num(x["distanza_atr"], 1)} ATR) · {quote(x["quote"])} quote · '
                    f'rischio {num(x["rischio"] / cambio)} €</div><div class="txt">{x["perche"]}</div>'
                    + (f'<div class="warn">{x["problema"]}</div>' if x["problema"] else "") + "</div>", unsafe_allow_html=True)
    tp = coach.take_profit(s, scelto)
    p = L.piano_distanza(ss.capitale * cambio, rischio, v["close"], scelto["distanza"])

    sezione("Su Capital.com, passo per passo" if v["colore"] == "VERDE" else "Esercizio: se fosse verde")
    passi = [("Cerca", f"<b>{L.nome_capital(ticker, nome)}</b> e tocca il riquadro blu <b>Compra</b>"),
             ("Quantità (Contratti)", f"<b>{quote(p['quote'])}</b> · cancella quella proposta dall'app"),
             ("Acquista quando il prezzo è pari a", f"ON → <b>{prezzo(p['ingresso'])}</b>"),
             ("Stop-loss", f"ON → <b>{num(p['distanza'], dec)}</b> punti sotto (≈ {prezzo(p['stop'])})"),
             ("Take profit", f"ON → <b>{num(p['distanza'] * L.RR, dec)}</b> punti sopra (≈ {prezzo(p['tp'])})"),
             ("Risultato possibile", f"rischi circa <b>{num(p['perdita'] / cambio)} €</b> per guadagnarne circa <b>{num(p['guadagno'] / cambio)} €</b>")]
    card("".join(f'<div class="passo"><div class="num">{i}</div><div class="txt"><b>{a}</b><br>{b}</div></div>'
                 for i, (a, b) in enumerate(passi, 1))
         + (f'<div class="nota" style="margin-top:6px">⚠️ {tp["avviso"]}</div>' if tp.get("avviso") else "")
         + ("" if v["colore"] == "VERDE" else '<div class="nota" style="margin-top:6px">Oggi il semaforo non è verde: '
            'questi numeri servono solo per imparare.</div>'))
    with st.expander("✅ Checklist prima di premere Compra"):
        voci = ["C'è scritto Demo nell'app", "Il semaforo è verde e ho letto il perché", "Ho scelto lo stop e so perché sta lì",
                "Ho scritto la quantità calcolata", "Stop-loss e Take profit sono attivi", "Ho scritto nel diario perché entro"]
        fatte = sum(st.checkbox(x, key=f"chk_{ticker}_{i}") for i, x in enumerate(voci))
        st.progress(fatte / len(voci), text=f"{fatte} su {len(voci)}")


# ==============================================================================
# CHAT CON IL BOT
# ==============================================================================
def analizza_per_chat(nome: str) -> dict | None:
    ticker = MERCATI.get(nome, (None, None))[0]
    d = dati_di(ticker) if ticker else None
    if d is None or len(d) < L.EMA_PERIODO + 50:
        return None
    df = prepara(d)
    v = L.valuta(df)
    s = coach.analizza(df)
    metodi = coach.metodi_stop(s, ss.capitale * cambio_eur(MERCATI[nome][1]), L.rischio_per(ticker, PIANO, ss.rischio))
    cons = next((m for m in metodi if m["consigliato"]), metodi[0])
    fare, _ = coach.consigli(s, True)
    return {"colore": v["colore"], "sintesi": v["sintesi"], "trend": s["trend"], "momento": s["momento"], "vol": s["vol"],
            "stop_nome": cons["nome"].lower(), "stop": prezzo(cons["stop"]), "tp": prezzo(coach.take_profit(s, cons)["tp"]),
            "consiglio": re.sub("<[^>]+>", "", fare[0]) if fare else "aspettare."}


def schermata_chat():
    m, ric = memoria(), memoria("ricerca_esito.json")
    etichetta, col, frase = stato_bot(m, ric)
    occhi = occhi_bot(m, ric)
    st.markdown(f'<div class="chat-hero">{robot(96, occhi)}<div class="top h1" style="font-size:1.25rem;font-weight:800;color:var(--testo)">'
                f'Sentinella</div><div class="nota"><span class="dot" style="background:{col}"></span> {etichetta} · '
                f'risponde con i dati veri del bot</div></div>', unsafe_allow_html=True)
    if not ss.chat:
        ss.chat = [("bot", f"Ciao! 👋 Sono Sentinella, il tuo bot di trading. {frase}<br>"
                           "Chiedimi pure qualcosa, oppure tocca uno dei suggerimenti.")]
    ctx = {"memoria": m, "ricerca": ric, "piano": PIANO, "panoramica": panoramica(), "analizza": analizza_per_chat,
           "notizie": lambda nome: notizie_di(MERCATI[nome][0]) if nome in MERCATI else [], "evento": eventi.evento_vicino}

    def chiedi(testo: str):
        ss.chat.append(("io", testo.replace("<", "&lt;")))
        try:
            ss.chat.append(("bot", chat_bot.rispondi(testo, ctx)))
        except Exception:
            ss.chat.append(("bot", "Ops, qualcosa è andato storto nel rispondere. Riprova tra poco."))

    testo = st.chat_input("Scrivi al bot…")
    if testo:
        chiedi(testo)
    if ss.get("domanda"):
        chiedi(ss.pop("domanda"))
    nuovo = ss.get("chat_visti", 1) < len(ss.chat)
    html = ""
    for i, (chi, t) in enumerate(ss.chat[-30:]):
        ultimo = i == len(ss.chat[-30:]) - 1
        if chi == "bot":
            anim = nuovo and ultimo
            html += (f'<div class="msg bot">{robot(28, occhi)}<div class="bub{" nuovo" if anim else ""}">'
                     + ('<span class="puntini"><i></i><i></i><i></i></span>' if anim else "") + f'<span class="tx">{t}</span></div></div>')
        else:
            html += f'<div class="msg io"><div class="bub">{t}</div></div>'
    st.markdown(html, unsafe_allow_html=True)
    ss.chat_visti = len(ss.chat)
    scelta = st.pills("Suggerimenti", chat_bot.SUGGERIMENTI, key=f"sugg_{len(ss.chat)}", label_visibility="collapsed")
    if scelta:
        chiedi(scelta)
        st.rerun()
    if len(ss.chat) > 2:
        components.html("<script>const d=window.parent.document;const m=d.querySelectorAll('.msg');"
                        "if(m.length)m[m.length-1].scrollIntoView({behavior:'smooth',block:'center'});</script>", height=0)
    if len(ss.chat) > 1:
        st.button("Nuova chat", icon=":material/refresh:", on_click=lambda: ss.update(chat=[]))
    st.markdown('<div class="nota" style="text-align:center;margin-top:8px">Scopo didattico, non è consulenza finanziaria.</div>',
                unsafe_allow_html=True)


# ==============================================================================
# IMPARA
# ==============================================================================
LEZIONI = [
    ("shield", "Perché il rischio zero non esiste", """
Nessuno sa cosa farà il prezzo domani. Ogni strategia ha operazioni vincenti e perdenti: chi promette guadagni sicuri
ti sta vendendo qualcosa. La differenza la fa **perdere poco quando sbagli**.

| Se perdi | Per tornare in pari ti serve |
|---|---|
| −10% | +11% |
| −25% | +33% |
| −50% | +100% |
| −75% | +300% |
"""),
    ("show_chart", "EMA 200, RSI e ATR in parole semplici", f"""
- **EMA 200 → il trend.** Media dei prezzi degli ultimi 200 giorni circa. Sopra = trend positivo, sotto = negativo: non si compra.
- **RSI → il momento.** Da 0 a 100. Tra {L.RSI_MIN} e {L.RSI_MAX} in un trend positivo il prezzo ha fatto una pausa. Sopra {L.RSI_TIRATO} è tirato.
- **ATR → la volatilità.** Quanto si muove in media in un giorno. Serve a mettere lo stop fuori dal rumore.
"""),
    ("target", "Dove mettere lo stop loss (e dove no)", """
1. Si decide **prima** di entrare e si imposta **insieme** all'ordine.
2. Meglio **un po' sotto il minimo recente**, se è a una distanza sensata (1,5-3,5 ATR); altrimenti **2 ATR**.
3. **Mai troppo stretto** (sotto 1 ATR): lo tocca il rumore di una giornata.
4. **Mai allontanarlo** dopo: è così che una piccola perdita diventa grande.
5. Si può **avvicinare** quando il prezzo sale (al pareggio dopo +1 volta il rischio).
6. **La quantità viene dallo stop**: stop più lontano = meno quote, rischio sempre uguale.
"""),
    ("percent", "La regola dell'1%", """
Su una singola operazione non si rischia mai più dell'**1% del capitale** (0,5% sulle cripto).
Anche 10 perdite di fila lasciano circa il 90% del conto. La formula:
**quote = (capitale × 1%) ÷ (prezzo di entrata − stop loss)**.
"""),
    ("balance", "Perché vincere spesso non basta", """
Nei test, un take profit vicino vince il 78% delle volte ma **perde soldi**: tante piccole vincite, poi uno stop se le mangia tutte.
Con take profit al doppio dello stop (1:2) basta vincere circa 1 volta su 3 per non perdere.
"""),
    ("checklist", "Le regole d'oro", """
1. Prima il **Demo**, poi forse i soldi veri.
2. Mai più dell'**1%** per operazione.
3. **Stop sempre**, deciso prima, mai spostato più lontano.
4. Solo **a favore del trend**.
5. Dopo 3 perdite di fila, **pausa**.
6. Tieni un **diario**.
7. Il bot è un aiuto, **non un oracolo**.
"""),
]


def schermata_impara():
    testata("Impara", '<span class="pill">6 lezioni</span>')
    st.markdown(f'<div class="bot-card" style="margin-top:0">{robot(44)}<div class="txt">Lezioni brevi, una alla volta. '
                'Sono le stesse regole che seguo io quando opero. Se hai un dubbio, chiedimelo in <b>chat</b>.</div></div>',
                unsafe_allow_html=True)
    for icona, titolo, testo in LEZIONI:
        with st.expander(f":material/{icona}: {titolo}"):
            st.markdown(testo)
    sezione("Calcolatrice della posizione")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        def leggi(testo: str) -> float:
            try:
                return float(testo.replace(".", "").replace(",", ".") if "," in testo else testo)
            except ValueError:
                return 0.0
        entrata = leggi(c1.text_input("Prezzo di entrata", "50,00"))
        stop = leggi(c2.text_input("Stop loss", "48,00"))
        if entrata <= 0 or stop <= 0:
            st.error("Scrivi i prezzi con i numeri, per esempio 50,25.")
            return
        if stop >= entrata:
            st.error("Per un acquisto lo stop deve stare sotto l'entrata.")
        else:
            dist = entrata - stop
            q = min(ss.capitale * ss.rischio / 100 / dist, ss.capitale / entrata)
            st.markdown(f'<div class="txt">Con {num(ss.capitale, 0)} € e rischio {pct(ss.rischio)}%: compri <b>{quote(q)}</b> quote, '
                        f'take profit a <b>{prezzo(entrata + 2 * dist)}</b>. Se va male perdi circa <b>{num(q * dist)} €</b>, '
                        f'se va bene guadagni circa <b>{num(q * dist * 2)} €</b>.</div>', unsafe_allow_html=True)


# ==============================================================================
# ALTRO: piano, ricerca, verifica sul passato, impostazioni
# ==============================================================================
def schermata_altro():
    testata("Altro")
    ric = memoria("ricerca_esito.json")
    vista = st.segmented_control("Sezione", ["Piano", "Ricerca", "Backtest", "Opzioni"], default="Piano", required=True,
                                 key="altro_vista", label_visibility="collapsed", width="stretch")
    P = PIANO
    if vista == "Piano":
        cap = float(P.get("capitale", 0))
        voci = [("Capitale", f"{num(cap, 0)} €", "Palestra sul Demo" if P.get("palestra") else "il piano"),
                ("Obiettivo", f"{num(float(P.get('obiettivo', 0) or 0), 0)} €", "sul Demo"),
                ("Rischio", f"{pct(P.get('rischio_per_operazione', 1))}%", f"cripto {pct(P.get('rischio_cripto', 0.5))}%"),
                ("Max aperte", str(P.get("max_posizioni_aperte", 3)), "operazioni insieme"),
                ("Stop giorno", f"−{P.get('stop_giornaliero_pct', 2)}%", f"−{num(cap * P.get('stop_giornaliero_pct', 2) / 100, 0)} €"),
                ("Stop mese", f"−{P.get('stop_mensile_pct', 8)}%", f"−{num(cap * P.get('stop_mensile_pct', 8) / 100, 0)} €")]
        st.markdown('<div class="griglia2">' + "".join(f'<div class="mini"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
                                                       for k, v, s in voci) + "</div>", unsafe_allow_html=True)
        sezione("Il percorso")
        for i, f in enumerate(P.get("fasi", []), 1):
            card(f'<div class="passo" style="border:none;padding:0"><div class="num">{i}</div><div>'
                 f'<div class="t">{f["nome"]} <span class="nota">· {f["durata"]}</span></div><div class="txt">{f["cosa"]}</div>'
                 f'<div class="nota" style="margin-top:4px">🎯 {f["traguardo"]}</div></div></div>')
    elif vista == "Ricerca":
        if not ric:
            card('<div class="txt">La ricerca non è ancora disponibile.</div>')
            return
        v = ric.get("vincitrice")
        card(f'<div class="t">{"✅ Regola promossa" if v else "Nessuna regola promossa"}</div>'
             f'<div class="txt">{("Strategia " + v["strategia"] + ", take profit 1:" + str(int(v["rr"]))) if v else "Con i costi reali nessuna combinazione ha un vantaggio affidabile anche sui mercati mai visti. Per questo il bot opera in Palestra: per studiare."}'
             f'</div><div class="nota" style="margin-top:6px">Ricerca del {pd.Timestamp(ric["data"]):%d/%m/%Y} · si ripete ogni domenica</div>')
        conf = ric.get("configurazioni") or []
        if conf:
            st.dataframe(pd.DataFrame([{"Strategia": c["strategia"], "TP": f"1:{c['rr']:.0f}", "Pareggio": "sì" if c["pareggio"] else "no",
                                        "Quando": c["filtro"], "PF 20 mercati": c["base"]["profit_factor"],
                                        "PF mai visti": c["mai_visti"]["profit_factor"], "OK": "✅" if c["promossa"] else ""}
                                       for c in conf]), hide_index=True, width="stretch")
            st.markdown('<div class="nota">PF = profit factor: guadagni ÷ perdite. Sopra 1,2 su entrambi i gruppi la regola viene promossa.</div>',
                        unsafe_allow_html=True)
    elif vista == "Backtest":
        card('<div class="txt">Le regole del semaforo provate sugli ultimi 3 anni dei 20 mercati, con spread e commissioni notturne.</div>')
        if st.button("Esegui la verifica", type="primary", width="stretch", icon=":material/play_arrow:"):
            ss.bt = True
        if ss.get("bt"):
            with st.spinner("Rigioco 3 anni di mercati…"):
                try:
                    r = calcola_backtest(float(P.get("capitale", 1000)))
                except Exception:
                    r = {"n": 0}
            if not r.get("n"):
                st.error("Non sono riuscito a completare la verifica. Riprova più tardi.")
                return
            st.plotly_chart(grafico_linea(r["curva"], 200, base=float(P.get("capitale", 1000))), width="stretch",
                            config={"displayModeBar": False})
            giudizio, spiegazione = backtest.verdetto(r)
            st.markdown('<div class="griglia2">' + "".join(
                f'<div class="mini"><div class="k">{k}</div><div class="v">{val}</div></div>'
                for k, val in [("Risultato", f"{r['rendimento_pct']:+.1f}%".replace(".", ",")), ("All'anno", f"{r['annuo_pct']:+.1f}%".replace(".", ",")),
                               ("Vinte", f"{r['win_rate']:.0f}%"), ("Discesa peggiore", f"{r['max_dd_pct']:.1f}%".replace(".", ","))])
                + "</div>", unsafe_allow_html=True)
            card(f'<div class="txt"><b>{giudizio[:1].upper() + giudizio[1:]}.</b> {spiegazione}</div>')
    else:
        st.number_input("Capitale per i calcoli (€)", min_value=100.0, step=100.0, key="capitale")
        st.select_slider("Rischio per operazione", options=[0.25, 0.5, 0.75, 1.0], key="rischio",
                         format_func=lambda x: f"{pct(x)}% del capitale")
        st.markdown('<div class="nota">Servono per i numeri dell\'app (quote, stop, risultati possibili). Il bot usa il suo piano.</div>',
                    unsafe_allow_html=True)
        card('<div class="t">Comandi del bot su Telegram</div><div class="txt">/stato · /resoconto · /stop · /riprendi</div>')


# ==============================================================================
# INSTRADAMENTO + BARRA IN BASSO
# ==============================================================================
if ss.pagina not in PAGINE:
    ss.pagina = "home"
ss.barra = ss.pagina
{"home": schermata_home, "mercati": schermata_mercati, "chat": schermata_chat,
 "impara": schermata_impara, "altro": schermata_altro}[ss.pagina]()

with st.container(key="navbar"):
    st.segmented_control("Navigazione", list(PAGINE), format_func=lambda k: PAGINE[k], required=True, key="barra",
                         on_change=da_barra, label_visibility="collapsed", width="stretch")
