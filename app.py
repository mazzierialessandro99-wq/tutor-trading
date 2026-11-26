"""
TUTOR DI TRADING — dashboard personale (solo analisi e formazione).
NON invia ordini: gli ordini li inserisci tu, a mano, sul conto DEMO del tuo broker.

Avvio sul PC:  streamlit run app.py
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import importlib

import logica as L
import capital, sentinella, backtest, coach  # noqa: E401

# Streamlit Cloud, dopo un aggiornamento, ricarica solo questo file: i moduli importati potrebbero
# restare alla versione vecchia. Li ricarichiamo sempre, in ordine, così sono tutti aggiornati.
L = importlib.reload(L)
capital = importlib.reload(capital)
sentinella = importlib.reload(sentinella)
backtest = importlib.reload(backtest)
coach = importlib.reload(coach)

st.set_page_config(page_title="Tutor di Trading", page_icon="📈", layout="centered",
                   initial_sidebar_state="collapsed")

# ==============================================================================
# TEMA: segue il telefono (chiaro / scuro)
# ==============================================================================
SCURO = (getattr(st.context.theme, "type", None) or "dark") == "dark"

if SCURO:
    T = dict(bg="#111312", surf="#1b1e1d", surf2="#232725", bordo="#2c302e", testo="#f0efec", testo2="#c3c2b7",
             muto="#9a998f", griglia="#232725", su="#199e70", giu="#e66767", ema="#3987e5", rsi="#9085e9",
             atr="#c98500", ombra="0 1px 0 rgba(255,255,255,.03)", hero1="#1d3149", hero2="#16201d")
else:
    T = dict(bg="#f4f4f1", surf="#ffffff", surf2="#f0efec", bordo="#e4e3dd", testo="#0b0b0b", testo2="#52514e",
             muto="#6b6a63", griglia="#ecebe6", su="#1baf7a", giu="#e34948", ema="#2a78d6", rsi="#6250d6",
             atr="#c98500", ombra="0 1px 3px rgba(20,20,10,.06)", hero1="#dcebfb", hero2="#eef6f1")

# Colori di stato: riservati al semaforo. Il giallo come testo su fondo chiaro va scurito per leggerlo.
STATO = {"VERDE": "#0ca30c", "GIALLO": "#fab219", "ROSSO": "#d03b3b"}
STATO_TESTO = {"VERDE": "#0ca30c" if SCURO else "#0a7f0a", "GIALLO": "#fab219" if SCURO else "#9a6700",
               "ROSSO": "#e05555" if SCURO else "#c0302f"}
ETICHETTA = {"VERDE": "Verde", "GIALLO": "Giallo", "ROSSO": "Rosso"}
PLURALE = {"VERDE": "verdi", "GIALLO": "gialli", "ROSSO": "rossi"}
BREVE = {"VERDE": "Opportunità", "GIALLO": "Attendere", "ROSSO": "Non operare"}

variabili = ";".join(f"--{k}:{v}" for k, v in T.items())
st.markdown(f"<style>:root{{{variabili}}}</style>", unsafe_allow_html=True)
st.markdown(
    """
<style>
/* ---- base ---- */
.stApp {background: var(--bg);}
[data-testid="stHeader"], [data-testid="stDecoration"] {display: none;}
.block-container {padding: 0.8rem 1rem 5rem; max-width: 720px;}
h1, h2, h3, h4 {letter-spacing: -0.015em;}
p, li {line-height: 1.55;}

/* ---- barra in alto ---- */
.st-key-topbar {align-items: center; margin-bottom: .2rem;}
.brand {font-weight: 800; font-size: 1.25rem; color: var(--testo); line-height: 1.1;}
.brand small {display: block; font-weight: 500; font-size: .74rem; color: var(--muto); letter-spacing: .02em;}
.st-key-topbar [data-testid="stPopover"] button {border-radius: 999px; padding: 4px 14px; font-weight: 600;
    background: var(--surf); border: 1px solid var(--bordo);}

/* ---- navigazione ---- */
.st-key-nav {position: sticky; top: 0; z-index: 50; background: var(--bg); padding: 6px 0 8px;}
.st-key-nav [data-testid="stButtonGroup"] {width: 100%;}
.st-key-nav button {flex: 1; border-radius: 12px !important; font-weight: 600; min-height: 42px; padding: 4px 2px !important; min-width: 0 !important;}
.st-key-nav button p {font-size: .8rem; white-space: nowrap; overflow: visible; letter-spacing: -.01em;}
.st-key-nav button > div {gap: 3px;}

/* ---- riquadri ---- */
.card {background: var(--surf); border: 1px solid var(--bordo); border-radius: 18px; padding: 14px 16px;
       margin: 10px 0; box-shadow: var(--ombra); color: var(--testo);}
.card .txt, .txt {color: var(--testo2); font-size: .93rem; line-height: 1.5;}
.card b, .txt b {color: var(--testo);}
.sezione {font-weight: 800; font-size: 1.05rem; color: var(--testo); margin: 22px 2px 4px;}
.nota {color: var(--muto); font-size: .8rem; margin: 4px 2px;}

/* ---- riepilogo di oggi ---- */
.oggi {border-radius: 22px; padding: 18px; margin: 6px 0 14px; border: 1px solid var(--bordo);
       background: linear-gradient(135deg, var(--hero1), var(--hero2));}
.oggi .t {font-size: .78rem; font-weight: 700; letter-spacing: .06em; color: var(--muto); text-transform: uppercase;}
.oggi .h {font-size: 1.35rem; font-weight: 800; color: var(--testo); margin: 4px 0 12px; line-height: 1.25;}
.conti {display: flex; gap: 8px; flex-wrap: wrap;}
.conto {display: flex; align-items: center; gap: 7px; background: var(--surf); border: 1px solid var(--bordo);
        border-radius: 999px; padding: 5px 12px 5px 8px; font-weight: 700; color: var(--testo); font-size: .9rem;}
.pall {width: 12px; height: 12px; border-radius: 50%; display: inline-block;}

/* ---- schede degli asset (tutta la scheda è toccabile) ---- */
[class*="st-key-asset_"] {position: relative;}
[class*="st-key-asset_"] [data-testid="stMarkdown"], [class*="st-key-asset_"] [data-testid="stMarkdown"] > div,
[class*="st-key-asset_"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
[class*="st-key-asset_"] [class*="st-key-apri_"] {position: absolute !important; inset: 0; width: 100% !important; height: 100% !important; z-index: 3; margin: 0;}
[class*="st-key-asset_"] [class*="st-key-apri_"] * {width: 100% !important; height: 100% !important;}
[class*="st-key-asset_"] [class*="st-key-apri_"] button {opacity: 0; cursor: pointer;}
.acard {display: flex; align-items: center; gap: 12px; background: var(--surf); border: 1px solid var(--bordo);
        border-radius: 18px; padding: 12px 14px; box-shadow: var(--ombra); transition: transform .08s;}
[class*="st-key-asset_"]:active .acard {transform: scale(.985);}
.luce-mini {flex: 0 0 auto; width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center;
            justify-content: center;}
.luce-mini span {width: 14px; height: 14px; border-radius: 50%;}
.ainfo {flex: 1; min-width: 0;}
.anome {font-weight: 700; color: var(--testo); font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.asub {font-size: .8rem; font-weight: 600;}
.spark {flex: 0 0 64px;}
.adx {text-align: right; flex: 0 0 auto;}
.aprezzo {font-weight: 700; color: var(--testo); font-size: .95rem;}
.avar {font-size: .78rem; font-weight: 700;}
.chev {color: var(--muto); font-size: 1.4rem; margin-left: 2px;}

/* ---- dettaglio ---- */
.st-key-indietro button {border: none; background: transparent; padding: 0; color: var(--ema); font-weight: 600;}
.titolo {font-size: 1.6rem; font-weight: 800; color: var(--testo); margin: 2px 0 0; line-height: 1.15;}
.sottotit {color: var(--muto); font-size: .85rem; margin-bottom: 8px;}
.sem {display: flex; gap: 16px; align-items: center; border-radius: 22px; padding: 16px; margin: 8px 0 12px;
      border: 1px solid;}
.luci {display: flex; flex-direction: column; gap: 7px; background: #0d0f0e; padding: 9px 8px; border-radius: 16px;}
.luce {width: 24px; height: 24px; border-radius: 50%; background: #2a2d2c;}
.sem-colore {font-size: 1.6rem; font-weight: 800; letter-spacing: .02em; line-height: 1.1;}
.sem-txt {color: var(--testo); margin-top: 3px; font-size: 1rem; line-height: 1.4;}
.sem-meta {color: var(--muto); font-size: .78rem; margin-top: 6px;}
.tiles {display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 4px 0 6px;}
@media (max-width: 640px) {.tiles {grid-template-columns: repeat(2, 1fr);}}
.tile {background: var(--surf); border: 1px solid var(--bordo); border-radius: 16px; padding: 10px 12px; box-shadow: var(--ombra);}
.tile .k {color: var(--muto); font-size: .75rem; font-weight: 600;}
.tile .v {font-size: 1.25rem; font-weight: 800; color: var(--testo); margin: 1px 0;}
.tile .s {color: var(--muto); font-size: .75rem;}
.spia {display: flex; gap: 12px; align-items: flex-start;}
.spia .ico {font-size: 1.25rem; line-height: 1.4;}
.spia .tit {font-weight: 700; margin-bottom: 2px; color: var(--testo);}
.passo {display: flex; gap: 14px; align-items: flex-start; background: var(--surf); border: 1px solid var(--bordo);
        border-radius: 18px; padding: 14px 16px; margin: 10px 0; box-shadow: var(--ombra);}
.num {flex: 0 0 32px; height: 32px; border-radius: 50%; background: #0ca30c1f; border: 1.5px solid #0ca30c;
      color: #0ca30c; font-weight: 800; display: flex; align-items: center; justify-content: center;}
.passo .tit {font-weight: 700; color: var(--testo); margin-bottom: 2px;}
.passo .val {font-size: 1.4rem; font-weight: 800; color: var(--testo); margin: 1px 0 3px;}
.campi {display: grid; grid-template-columns: auto 1fr; gap: 5px 14px; margin-top: 8px; font-size: .92rem;
        background: var(--surf2); border-radius: 12px; padding: 10px 12px;}
.campi span:nth-child(odd) {color: var(--muto);}
.campi.colonna {grid-template-columns: 1fr; gap: 0;}
.campi.colonna span:nth-child(odd) {font-size: .8rem; margin-top: 8px;}
.campi.colonna span:nth-child(1) {margin-top: 0;}
.campi span:nth-child(even) {font-weight: 700; color: var(--testo);}

/* ---- widget di Streamlit più "da app" ---- */
[data-testid="stExpander"] details {border-radius: 16px; background: var(--surf); border-color: var(--bordo);}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {border-radius: 12px;}
.stButton button {border-radius: 12px; font-weight: 600;}

/* ---- bot ---- */
.bot-hero {display: flex; gap: 14px; align-items: flex-start; border-radius: 22px; padding: 18px; margin: 4px 0 6px;
           border: 1px solid var(--bordo); background: linear-gradient(135deg, var(--hero1), var(--hero2));}
.bot-av {flex: 0 0 52px; height: 52px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
         font-size: 1.8rem; background: var(--surf); border: 1px solid var(--bordo);}
.bot-nome {font-weight: 800; font-size: 1.2rem; color: var(--testo); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;}
.bot-stato {font-size: .75rem; font-weight: 800; padding: 3px 10px; border-radius: 999px; border: 1px solid;}
.bot-frase {color: var(--testo); margin-top: 6px; font-size: .95rem; line-height: 1.5;}
.bot-meta {color: var(--muto); font-size: .78rem; margin-top: 8px;}
.tl {padding: 6px 14px 10px;}
.tl-giorno {font-size: .72rem; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; color: var(--muto);
            margin: 12px 0 4px;}
.tl-voce {display: flex; gap: 10px; align-items: flex-start; padding: 7px 0; border-bottom: 1px solid var(--bordo);}
.tl-voce:last-child {border-bottom: none;}
.tl-ora {flex: 0 0 42px; color: var(--muto); font-size: .8rem; padding-top: 2px;}
.tl-ico {flex: 0 0 22px;}
.tl-tit {color: var(--testo); font-size: .9rem;}
.tl-mot {color: var(--muto); font-size: .8rem; line-height: 1.4;}

/* ---- tutor ---- */
.chips {display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 10px;}
.chip {display: flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 999px; font-weight: 700;
       font-size: .86rem; background: var(--surf); border: 1px solid var(--bordo); color: var(--testo);}
.lista {margin: 4px 0 0; padding-left: 0; list-style: none;}
.lista li {position: relative; padding: 5px 0 5px 26px; color: var(--testo2); font-size: .93rem; line-height: 1.45;}
.lista li b {color: var(--testo);}
.lista li::before {position: absolute; left: 0; top: 4px; font-size: 1rem;}
.lista.si li::before {content: "✅";}
.lista.no li::before {content: "⛔";}
.stop-card {background: var(--surf); border: 1px solid var(--bordo); border-radius: 16px; padding: 12px 14px; margin: 8px 0;}
.stop-card.scelto {border: 1.5px solid var(--ema);}
.stop-top {display: flex; justify-content: space-between; align-items: baseline; gap: 10px;}
.stop-top .n {font-weight: 700; color: var(--testo);}
.stop-top .p {font-weight: 800; font-size: 1.15rem; color: var(--testo); white-space: nowrap;}
.badge {display: inline-block; font-size: .68rem; font-weight: 800; letter-spacing: .04em; padding: 2px 8px;
        border-radius: 999px; background: var(--ema); color: #fff; margin-left: 6px; vertical-align: middle;}
.stop-dati {display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 6px 0 4px; font-size: .82rem; color: var(--muto);}
.stop-dati b {color: var(--testo);}
.problema {color: var(--giu); font-size: .85rem; font-weight: 600; margin-top: 4px;}
</style>
""",
    unsafe_allow_html=True,
)


# ==============================================================================
# FORMATI
# ==============================================================================
def html_testo(s: str) -> str:
    """Converte il **grassetto** markdown in HTML (dentro i riquadri personalizzati)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def fmt_num(x: float, dec: int = 2) -> str:
    """Numero all'italiana: 1.234,56"""
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_prezzo(p: float) -> str:
    return fmt_num(p, 4 if abs(p) < 10 else 2)


def fmt_quote(q: float) -> str:
    return fmt_num(q, 0 if q >= 100 else 2 if q >= 1 else 4)


def fmt_pct(x: float) -> str:
    return fmt_num(x, 2).rstrip("0").rstrip(",")


# ==============================================================================
# DATI (yfinance: gratuiti e in ritardo)
# ==============================================================================
DEMO = os.environ.get("TUTOR_DEMO") == "1"   # solo per le prove dello sviluppatore, senza internet


def _dati_demo(ticker: str) -> pd.DataFrame:
    rng = np.random.default_rng(sum(map(ord, ticker)))
    n = 1300
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0007, 0.012, n)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + rng.uniform(0, .008, n))
    lo = np.minimum(op, close) * (1 - rng.uniform(0, .008, n))
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close}, index=idx)


@st.cache_data(ttl=3600, show_spinner=False)
def scarica(ticker: str) -> pd.DataFrame:
    """Ultimi 5 anni di candele giornaliere (200 giorni servono a 'scaldare' la EMA 200)."""
    if DEMO:
        return _dati_demo(ticker)
    import yfinance as yf
    df = yf.download(ticker, period="5y", interval="1d", auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def valuta_ticker(ticker: str) -> str:
    if DEMO:
        return "USD"
    try:
        import yfinance as yf
        return (yf.Ticker(ticker).fast_info.get("currency") or "USD").upper()
    except Exception:
        return "USD"


@st.cache_data(ttl=3600, show_spinner=False)
def cambio_eur(valuta: str) -> float | None:
    """Quante unità di `valuta` vale 1 euro (es. USD: circa 1,08)."""
    if valuta == "EUR":
        return 1.0
    if DEMO:
        return 1.08
    df = scarica(f"EUR{valuta}=X")
    return float(df["Close"].iloc[-1]) if not df.empty else None


def prepara(dati: pd.DataFrame) -> pd.DataFrame:
    """Indicatori + semaforo di ogni giornata (serve anche per i triangoli e il backtest)."""
    df = L.aggiungi_indicatori(dati)
    df["Semaforo"] = [
        L.semaforo_riga(c, e, r, rp, a)
        for c, e, r, rp, a in zip(df["Close"], df["EMA200"], df["RSI"], df["RSI"].shift(1), df["ATR"])
    ]
    return df.iloc[L.EMA_PERIODO:]


@st.cache_data(ttl=1800, show_spinner=False)
def panoramica() -> list[dict]:
    """Semaforo di tutti gli asset proposti, per la schermata iniziale (una sola richiesta a Yahoo)."""
    tickers = [t for t, _ in L.ASSET.values()]
    try:
        tutti = {t: _dati_demo(t) for t in tickers} if DEMO else sentinella.scarica_tutti(tickers)
    except Exception:
        tutti = {}
    righe = []
    for nome, (ticker, _) in L.ASSET.items():
        try:
            d = tutti.get(ticker)
            if d is None or len(d) < L.EMA_PERIODO + 20:
                continue
            v = L.valuta(L.aggiungi_indicatori(d))
            righe.append({"nome": nome, "ticker": ticker, "colore": v["colore"], "close": v["close"],
                          "var": (d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1) * 100,
                          "spark": d["Close"].iloc[-60:].tolist(), "data": v["data"]})
        except Exception:
            continue
    ordine = {"VERDE": 0, "GIALLO": 1, "ROSSO": 2}
    return sorted(righe, key=lambda r: ordine[r["colore"]])


# ==============================================================================
# STATO DELL'APP
# ==============================================================================
ss = st.session_state
PIANO = L.carica_piano()
ss.setdefault("capitale", float(PIANO.get("capitale", 1000)))
ss.setdefault("rischio", float(PIANO.get("rischio_per_operazione", 1.0)))
ss.setdefault("aperto", None)        # (nome, ticker) dell'asset aperto, None = elenco

PAGINE = ["🤖 Bot", "🚦 Segnali", "📋 Piano", "🎓 Impara", "🧪 Test"]

# ---- barra in alto: nome + impostazioni del conto ----
with st.container(key="topbar", horizontal=True, vertical_alignment="center", wrap=False):
    st.markdown('<div class="brand">📈 Tutor <small>CONTO DEMO</small></div>',
                unsafe_allow_html=True)
    if hasattr(st, "space"):
        st.space("stretch")
    with st.popover(f"💶 {fmt_num(ss.capitale, 0)} € · {fmt_pct(ss.rischio)}%"):
        st.markdown("**Il mio conto**")
        # I valori veri stanno in ss.capitale / ss.rischio; i widget hanno chiavi proprie
        # (Streamlit cancella lo stato dei widget quando non sono sullo schermo).
        st.number_input("Capitale (€)", min_value=100.0, step=100.0, value=float(ss.capitale), key="w_capitale",
                        on_change=lambda: ss.update(capitale=ss.w_capitale))
        st.select_slider("Rischio per operazione", options=[0.25, 0.5, 0.75, 1.0], value=ss.rischio, key="w_rischio",
                         format_func=lambda x: f"{fmt_pct(x)}% del capitale",
                         on_change=lambda: ss.update(rischio=ss.w_rischio),
                         help="La regola d'oro è non superare l'1%. Chi inizia può scendere allo 0,5%.")
        st.caption("Servono a calcolare quante quote comprare. Restano solo su questo dispositivo finché l'app è aperta.")

with st.container(key="nav"):
    pagina = st.segmented_control("Sezione", PAGINE, default=PAGINE[0], required=True, key="pagina",
                                  label_visibility="collapsed", width="stretch")


# ==============================================================================
# PEZZI GRAFICI
# ==============================================================================
def sparkline(valori: list[float], colore: str) -> str:
    v = np.array(valori, dtype=float)
    lo, hi = v.min(), v.max()
    y = 26 - (v - lo) / (hi - lo or 1) * 24
    x = np.linspace(1, 63, len(v))
    punti = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, y))
    return (f'<svg class="spark" width="64" height="28" viewBox="0 0 64 28">'
            f'<polyline points="{punti}" fill="none" stroke="{colore}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def scheda_asset(r: dict):
    col = r["colore"]
    su = r["var"] >= 0
    with st.container(key=f"asset_{r['ticker']}"):
        st.markdown(
            f"""
<div class="acard">
  <div class="luce-mini" style="background:{STATO[col]}22"><span style="background:{STATO[col]};
       box-shadow:0 0 10px {STATO[col]}"></span></div>
  <div class="ainfo"><div class="anome">{r['nome']}</div>
       <div class="asub" style="color:{STATO_TESTO[col]}">{ETICHETTA[col]} · {BREVE[col]}</div></div>
  {sparkline(r['spark'], T['su'] if r['spark'][-1] >= r['spark'][0] else T['giu'])}
  <div class="adx"><div class="aprezzo">{fmt_prezzo(r['close'])}</div>
       <div class="avar" style="color:{T['su'] if su else T['giu']}">{"▲" if su else "▼"} {fmt_num(abs(r['var']))}%</div></div>
  <div class="chev">›</div>
</div>""",
            unsafe_allow_html=True,
        )
        if st.button(f"Apri {r['nome']}", key=f"apri_{r['ticker']}"):
            ss.aperto = (r["nome"], r["ticker"])
            st.rerun()


def grafico(df: pd.DataFrame) -> go.Figure:
    verdi = df[df["Semaforo"] == "VERDE"]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.62, 0.2, 0.18],
                        subplot_titles=("Prezzo ed EMA 200 · trend", "RSI (14) · timing", "ATR (14) · volatilità"))
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                 name="Prezzo", increasing=dict(line=dict(color=T["su"], width=1), fillcolor=T["su"]),
                                 decreasing=dict(line=dict(color=T["giu"], width=1), fillcolor=T["giu"])), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA200"], name="EMA 200", line=dict(color=T["ema"], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=verdi.index, y=verdi["Low"] - verdi["ATR"] * 0.6, mode="markers",
                             name="Semaforo verde", marker=dict(symbol="triangle-up", size=11, color=STATO["VERDE"],
                                                                line=dict(width=1.5, color=T["bg"])),
                             hovertemplate="Semaforo verde<extra></extra>"), row=1, col=1)
    fig.add_shape(type="rect", xref="x2 domain", yref="y2", x0=0, x1=1, y0=L.RSI_MIN, y1=L.RSI_MAX,
                  fillcolor=STATO["VERDE"], opacity=0.16, line_width=0, layer="below")
    fig.add_shape(type="line", xref="x2 domain", yref="y2", x0=0, x1=1, y0=L.RSI_TIRATO, y1=L.RSI_TIRATO,
                  line=dict(color=T["muto"], width=1.2, dash="dot"))
    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI", line=dict(color=T["rsi"], width=2),
                             showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["ATR"], name="ATR", line=dict(color=T["atr"], width=2),
                             showlegend=False), row=3, col=1)

    fine = df.index[-1]
    inizio = fine - pd.Timedelta(days=365)
    vis = df[df.index >= inizio]
    pad = (vis["High"].max() - vis["Low"].min()) * 0.06
    fig.update_xaxes(range=[inizio, fine + pd.Timedelta(days=5)], rangeslider_visible=False, tickformat="%m/%y",
                     hoverformat="%d/%m/%Y", gridcolor=T["griglia"], showspikes=True, spikemode="across",
                     spikecolor=T["muto"], spikethickness=1)
    fig.update_yaxes(gridcolor=T["griglia"], zeroline=False, side="right")
    fig.update_yaxes(range=[vis["Low"].min() - pad, vis["High"].max() + pad], row=1, col=1)
    fig.update_yaxes(range=[0, 100], tickvals=[L.RSI_MIN, L.RSI_MAX, L.RSI_TIRATO], row=2, col=1)
    fig.update_yaxes(range=[0, vis["ATR"].max() * 1.15], row=3, col=1)
    fig.update_layout(height=600, template="plotly_dark" if SCURO else "plotly_white",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=4, r=4, t=28, b=4), hovermode="x unified", dragmode="pan",
                      font=dict(color=T["testo2"], size=12), separators=",.",
                      legend=dict(orientation="h", y=-0.05, x=0, font=dict(size=12)))
    fig.update_annotations(font=dict(size=12, color=T["muto"]), x=0, xanchor="left")
    return fig


def riquadro_semaforo(v: dict):
    col = v["colore"]
    luci = "".join(
        f'<span class="luce" style="{f"background:{STATO[c]};box-shadow:0 0 16px {STATO[c]}" if c == col else ""}"></span>'
        for c in ("ROSSO", "GIALLO", "VERDE"))
    st.markdown(
        f"""
<div class="sem" style="border-color:{STATO[col]}55; background:linear-gradient(135deg,{STATO[col]}26,var(--surf) 72%);">
  <div class="luci">{luci}</div>
  <div>
    <div class="sem-colore" style="color:{STATO_TESTO[col]}">{col}</div>
    <div class="sem-txt">{v["sintesi"]}</div>
    <div class="sem-meta">Ultima chiusura {v["data"]:%d/%m/%Y} · dati Yahoo Finance in ritardo</div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )


def tessere(v: dict, df: pd.DataFrame):
    var = (v["close"] / df["Close"].iloc[-2] - 1) * 100
    voci = [("Prezzo", fmt_prezzo(v["close"]),
             f'<span style="color:{T["su"] if var >= 0 else T["giu"]};font-weight:700">'
             f'{"▲" if var >= 0 else "▼"} {fmt_num(abs(var))}%</span>'),
            ("EMA 200", fmt_prezzo(v["ema"]), "trend"),
            ("RSI", f"{v['rsi']:.0f}", "timing"),
            ("ATR", fmt_num(v["atr"], 4 if v["close"] < 10 else 2), "volatilità")]
    st.markdown('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
        for k, val, s in voci) + "</div>", unsafe_allow_html=True)


def spie(v: dict):
    icone = {"ok": "✅", "forse": "⚠️", "no": "⛔", "info": "📏"}
    for stato, titolo, testo in v["spie"]:
        st.markdown(f'<div class="card spia"><div class="ico">{icone[stato]}</div>'
                    f'<div><div class="tit">{titolo}</div><div class="txt">{html_testo(testo)}</div></div></div>',
                    unsafe_allow_html=True)


def passo(n: int, titolo: str, valore: str, testo: str):
    st.markdown(f'<div class="passo"><div class="num">{n}</div><div style="flex:1">'
                f'<div class="tit">{titolo}</div><div class="val">{valore}</div>'
                f'<div class="txt">{html_testo(testo)}</div></div></div>', unsafe_allow_html=True)


def passi_operativi(p: dict, v: dict, nome: str, valuta: str, cambio: float, rischio_pct: float,
                    spiegazione_stop: str | None = None):
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta + " ")
    eur = lambda x: fmt_num(x / cambio)   # importo nella valuta dell'asset -> euro
    nota_cambio = "" if valuta == "EUR" else f" (prezzi in {valuta}, cambio 1 € = {fmt_num(cambio, 4)} {valuta})"
    dec = 4 if p["ingresso"] < 10 else 2

    passo(1, "Quante quote comprare", f"{fmt_quote(p['quote'])} quote",
          f"Impegni circa **{eur(p['impegno'])} €** del tuo capitale. Se tocca lo stop perdi al massimo circa "
          f"**{eur(p['perdita'])} €**, cioè il {fmt_pct(rischio_pct)}% del capitale{nota_cambio}."
          + (" ⚠️ Il numero è stato **ridotto** per non impegnare più del tuo capitale: il rischio reale è più basso."
             if p["limitato"] else ""))
    passo(2, "Prezzo di ingresso", f"{sim}{fmt_prezzo(p['ingresso'])}",
          "È l'ultima chiusura. I dati sono in ritardo: **controlla il prezzo vero sul broker**. "
          f"Se è già salito oltre **{sim}{fmt_prezzo(p['ingresso'] + 0.5 * v['atr'])}** (mezzo ATR), "
          "non inseguirlo: salta l'occasione.")
    passo(3, "Stop Loss", f"{sim}{fmt_prezzo(p['stop'])}",
          (spiegazione_stop + f" Distanza dall'ingresso: {sim}{fmt_num(p['distanza'], dec)}.") if spiegazione_stop else
          f"È {fmt_num(L.STOP_ATR, 0)} volte l'ATR sotto l'ingresso ({sim}{fmt_num(p['distanza'], dec)}). "
          "Così le normali oscillazioni di una o due giornate non ti fanno uscire per sbaglio; "
          "se invece il prezzo scende davvero fin lì, l'idea era sbagliata e si esce con una perdita piccola.")
    passo(4, "Take Profit", f"{sim}{fmt_prezzo(p['tp'])}",
          f"È a **{fmt_num(L.RR, 0)} volte** la distanza dello stop (rapporto 1:{fmt_num(L.RR, 0)}). "
          f"Se ci arriva guadagni circa **{eur(p['guadagno'])} €**: il doppio di quello che rischi.")
    ticker = L.ASSET.get(nome, (nome, None))[0]
    cerca = L.nome_capital(ticker, nome)
    d = fmt_num(p["distanza"], dec)
    d2 = fmt_num(p["distanza"] * L.RR, dec)
    st.markdown(
        f"""
<div class="passo"><div class="num">5</div><div style="flex:1">
  <div class="tit">Cosa fare nell'app Capital.com</div>
  <div class="txt">Controlla che in alto ci sia scritto <b>Demo</b>, cerca <b>{cerca}</b> e tocca il riquadro blu <b>Compra</b>:</div>
  <div class="campi colonna">
    <span>Quantità (Contratti)</span><span>{fmt_quote(p['quote'])}</span>
    <span>Acquista quando il prezzo è pari a</span><span>ON → {fmt_prezzo(p['ingresso'])}</span>
    <span>Stop-loss</span><span>ON → {d} punti sotto l'ingresso</span>
    <span>Take profit</span><span>ON → {d2} punti sopra l'ingresso</span>
  </div>
  <div class="txt" style="margin-top:8px">⚠️ <b>Cancella sempre la quantità che propone l'app</b> (es. 85 contratti
  vuol dire rischiare quasi tutto il conto) e scrivi <b>{fmt_quote(p['quote'])}</b>.<br>
  I prezzi di Capital.com possono differire un po' dai nostri: per stop e take profit conta la <b>distanza in punti</b>
  (con ingresso a {fmt_prezzo(p['ingresso'])} sono circa {fmt_prezzo(p['stop'])} e {fmt_prezzo(p['tp'])}).<br>
  Controlla il <b>requisito di margine</b>: deve essere una piccola parte del conto. Poi premi il pulsante blu
  <b>Compra</b> in basso e scrivi nel diario data, mercato e motivo.</div>
</div></div>""",
        unsafe_allow_html=True,
    )


def banner_assistente():
    if PIANO.get("modalita") == "automatico":
        st.markdown('<div class="card" style="display:flex;gap:12px;align-items:center;padding:12px 14px">'
                    '<div style="font-size:1.5rem">🤖</div><div class="txt"><b>Assistente automatico · conto Demo</b><br>'
                    'Controlla i mercati ogni 30 minuti e apre da solo le operazioni del piano. '
                    'Su Telegram: <b>/stato</b> · <b>/stop</b> · <b>/riprendi</b></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="card" style="display:flex;gap:12px;align-items:center;padding:12px 14px">'
                    '<div style="font-size:1.5rem">🔔</div><div class="txt"><b>Assistente in modalità avvisi</b><br>'
                    'Controlla i mercati ogni 30 minuti e ti scrive su Telegram quando un semaforo diventa verde.</div></div>',
                    unsafe_allow_html=True)


# ==============================================================================
# SEZIONE SEGNALI: elenco degli asset
# ==============================================================================
def schermata_elenco():
    with st.spinner("Controllo i mercati…"):
        righe = panoramica()
    if not righe:
        st.error("Non riesco a scaricare i prezzi in questo momento (Yahoo ogni tanto limita le richieste). "
                 "Riprova tra qualche minuto.")
        return

    n = {c: sum(r["colore"] == c for r in righe) for c in STATO}
    titolo = ("Oggi c'è un'occasione da guardare" if n["VERDE"] == 1 else
              f"Oggi ci sono {n['VERDE']} occasioni da guardare" if n["VERDE"] > 1 else
              "Oggi nessuna occasione: si aspetta")
    conti = "".join(f'<div class="conto"><span class="pall" style="background:{STATO[c]}"></span>'
                    f'{n[c]} {ETICHETTA[c].lower() if n[c] == 1 else PLURALE[c]}</div>' for c in STATO)
    data = max(r["data"] for r in righe)
    st.markdown(f'<div class="oggi"><div class="t">Semaforo di oggi · chiusura {data:%d/%m}</div>'
                f'<div class="h">{titolo}</div><div class="conti">{conti}</div></div>', unsafe_allow_html=True)

    banner_assistente()
    for r in righe:
        scheda_asset(r)

    st.markdown('<div class="sezione">Cerca un altro titolo</div>', unsafe_allow_html=True)
    with st.form("cerca", border=False):
        simbolo = st.text_input("Simbolo Yahoo Finance", placeholder="es. ENI.MI, TSLA, ETH-USD",
                                label_visibility="collapsed")
        if st.form_submit_button("Analizza", width="stretch") and simbolo.strip():
            ss.aperto = (simbolo.strip().upper(), simbolo.strip().upper())
            st.rerun()
    st.markdown('<div class="nota">Il simbolo lo trovi su finance.yahoo.com. Borsa italiana: aggiungi ".MI" (es. ENI.MI).</div>',
                unsafe_allow_html=True)


# ==============================================================================
# SEZIONE SEGNALI: dettaglio di un asset
# ==============================================================================
def sezione_coach(df: pd.DataFrame, v: dict, nome: str, ticker: str, valuta: str, cambio: float,
                  rischio: float) -> tuple[float, str]:
    """Il tutor sul mercato: situazione, cosa fare e non fare, scelta dello stop. Restituisce (distanza, spiegazione)."""
    s = coach.analizza(df)
    ricerca_ok = bool((memoria_bot("ricerca_esito.json") or {}).get("vincitrice"))
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta + " ")
    eur = lambda x: fmt_num(x / cambio)
    dec = 4 if s["close"] < 10 else 2

    st.markdown('<div class="sezione">🧭 Il tuo tutor su questo mercato</div>', unsafe_allow_html=True)
    chips = "".join(f'<div class="chip">{coach.ETICHETTE[k][s[k]][0]} {coach.ETICHETTE[k][s[k]][1]}</div>'
                    for k in ("trend", "momento", "vol"))
    st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    fare, non = coach.consigli(s, ricerca_ok)
    st.markdown('<div class="card"><div class="tit" style="font-weight:800">Cosa fare</div><ul class="lista si">'
                + "".join(f"<li>{x}</li>" for x in fare) + "</ul></div>", unsafe_allow_html=True)
    st.markdown('<div class="card"><div class="tit" style="font-weight:800">Cosa non fare</div><ul class="lista no">'
                + "".join(f"<li>{x}</li>" for x in non) + "</ul></div>", unsafe_allow_html=True)

    # ---- stop loss ----
    st.markdown('<div class="sezione">🎯 Dove mettere lo stop loss</div>', unsafe_allow_html=True)
    st.markdown('<div class="nota">Lo stop si decide <b>prima</b> di entrare. Qualunque metodo scegli, il rischio in euro '
                'resta lo stesso: cambia la quantità. Stop più lontano = meno quote.</div>', unsafe_allow_html=True)
    metodi = coach.metodi_stop(s, ss.capitale * cambio, rischio)
    consigliato = next(m for m in metodi if m["consigliato"])
    validi = [m for m in metodi if m["distanza"] > 0]
    brevi = {"atr": "Volatilità", "struttura": "Minimo recente", "percentuale": "Percentuale"}
    scelta = st.segmented_control("Metodo di stop", [m["chiave"] for m in validi], default=consigliato["chiave"],
                                  required=True, format_func=lambda k: brevi[k], key=f"stop_{ticker}",
                                  label_visibility="collapsed", width="stretch")
    scelto = next(m for m in validi if m["chiave"] == scelta)
    for m in validi:
        st.markdown(
            f'<div class="stop-card{" scelto" if m is scelto else ""}"><div class="stop-top">'
            f'<div class="n">{m["nome"]}{"<span class=badge>CONSIGLIATO</span>" if m["consigliato"] else ""}</div>'
            f'<div class="p">{sim}{fmt_prezzo(m["stop"])}</div></div>'
            f'<div class="stop-dati"><span>distanza <b>{fmt_num(m["distanza"], dec)}</b> ({fmt_num(m["distanza_atr"], 1)} ATR)</span>'
            f'<span>quote <b>{fmt_quote(m["quote"])}</b></span><span>rischio <b>{eur(m["rischio"])} €</b></span></div>'
            f'<div class="txt">{m["perche"]}</div>'
            + (f'<div class="problema">⚠️ {m["problema"]}</div>' if m["problema"] else "")
            + (f'<div class="nota" style="margin:6px 0 0">💡 {consigliato["motivo_scelta"]}</div>' if m["consigliato"] else "")
            + "</div>", unsafe_allow_html=True)

    # grafico: ingresso, stop, take profit e minimo recente
    tp = coach.take_profit(s, scelto)
    vis = df.iloc[-90:]
    fig = go.Figure(go.Candlestick(x=vis.index, open=vis["Open"], high=vis["High"], low=vis["Low"], close=vis["Close"],
                                   increasing=dict(line=dict(color=T["su"], width=1), fillcolor=T["su"]),
                                   decreasing=dict(line=dict(color=T["giu"], width=1), fillcolor=T["giu"]),
                                   name="Prezzo", showlegend=False))
    for y, testo, colore, tratto, pos in [(s["close"], "Ingresso", T["testo2"], "solid", "top left"),
                                          (scelto["stop"], "Stop loss", T["giu"], "solid", "bottom left"),
                                          (tp["tp"], "Take profit", T["su"], "solid", "top left"),
                                          (s["supporto"], "Minimo recente", T["muto"], "dot", "top right")]:
        fig.add_hline(y=y, line=dict(color=colore, width=1.6 if tratto == "solid" else 1, dash=tratto),
                      annotation_text=f"{testo} {fmt_prezzo(y)}", annotation_position=pos,
                      annotation_font=dict(size=11, color=colore))
    fig.update_layout(height=320, template="plotly_dark" if SCURO else "plotly_white",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      margin=dict(l=4, r=4, t=10, b=4), dragmode="pan", font=dict(color=T["testo2"], size=11),
                      xaxis_rangeslider_visible=False)
    fig.update_xaxes(gridcolor=T["griglia"], tickformat="%d/%m")
    fig.update_yaxes(gridcolor=T["griglia"], side="right")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    st.markdown(f'<div class="card"><div class="tit" style="font-weight:800">🏁 Take profit: {sim}{fmt_prezzo(tp["tp"])}</div>'
                f'<div class="txt">Il doppio della distanza dello stop (1:{fmt_num(L.RR, 0)}): se va bene guadagni circa '
                f'{eur(scelto["rischio"] * L.RR)} €, se va male perdi circa {eur(scelto["rischio"])} €.</div>'
                + (f'<div class="nota" style="margin:6px 0 0">⚠️ {tp["avviso"]}</div>' if tp["avviso"] else "")
                + "</div>", unsafe_allow_html=True)

    # ---- checklist ----
    st.markdown('<div class="sezione">📋 Prima di premere Compra</div>', unsafe_allow_html=True)
    voci = ["In alto nell'app c'è scritto Demo", "Il semaforo è verde e ho letto il perché",
            "Ho scelto lo stop e so perché sta lì", "Ho scritto la quantità calcolata (non quella proposta dall'app)",
            "Stop-loss e Take profit sono attivi nel modulo d'ordine", "Ho scritto nel diario perché entro"]
    fatte = sum(st.checkbox(x, key=f"chk_{ticker}_{i}") for i, x in enumerate(voci))
    st.progress(fatte / len(voci), text=f"{fatte} su {len(voci)}")
    if fatte == len(voci):
        st.markdown('<div class="nota">✅ Tutto pronto. Ricorda: dopo l\'ingresso stop e take profit non si toccano più.</div>',
                    unsafe_allow_html=True)
    return scelto["distanza"], f"Metodo «{scelto['nome']}»: {scelto['perche']}"


def schermata_dettaglio(nome: str, ticker: str):
    if st.button("‹ Tutti gli asset", key="indietro"):
        ss.aperto = None
        st.rerun()

    st.markdown(f'<div class="titolo">{nome}</div><div class="sottotit">{ticker} · candele giornaliere</div>',
                unsafe_allow_html=True)
    with st.spinner("Scarico i prezzi…"):
        try:
            dati = scarica(ticker)
        except Exception:
            dati = pd.DataFrame()
    if len(dati) < L.EMA_PERIODO + 50:
        st.error(f"Non trovo abbastanza dati per **{ticker}**. Controlla il simbolo o riprova tra qualche minuto.")
        return

    df = prepara(dati)
    v = L.valuta(df)
    riquadro_semaforo(v)
    tessere(v, df)

    st.markdown('<div class="sezione">Grafico</div>', unsafe_allow_html=True)
    st.plotly_chart(grafico(df), width="stretch", config={"displayModeBar": False, "scrollZoom": False})
    st.markdown('<div class="nota">Ultimi 12 mesi: trascina per tornare indietro. ▲ verdi = giorni con semaforo verde. '
                f'Fascia verde nell\'RSI = zona del ritracciamento ({L.RSI_MIN}-{L.RSI_MAX}).</div>',
                unsafe_allow_html=True)

    st.markdown(f'<div class="sezione">Perché è {v["colore"].lower()}</div>', unsafe_allow_html=True)
    spie(v)

    valuta = L.ASSET.get(nome, (None, None))[1] or valuta_ticker(ticker)
    cambio = cambio_eur(valuta)
    if cambio is None:
        st.warning(f"Non riesco a leggere il cambio euro/{valuta}: i calcoli sono fatti come se 1 € = 1 {valuta}.")
        cambio = 1.0
    rischio = L.rischio_per(ticker, PIANO, ss.rischio)
    distanza, spiegazione_stop = sezione_coach(df, v, nome, ticker, valuta, cambio, rischio)
    p = L.piano_distanza(ss.capitale * cambio, rischio, v["close"], distanza)

    if v["colore"] == "VERDE":
        st.markdown('<div class="sezione">✅ Cosa fare, passo per passo</div>', unsafe_allow_html=True)
        passi_operativi(p, v, nome, valuta, cambio, rischio, spiegazione_stop)
    else:
        cosa = ("Niente: **non si compra**. Torna all'elenco e guarda un altro asset, oppure ricontrolla domani."
                if v["colore"] == "ROSSO" else
                "**Aspetta.** Diventa verde quando il trend è chiaramente positivo e l'RSI, dopo essere sceso "
                f"tra {L.RSI_MIN} e {L.RSI_MAX}, ricomincia a salire. Ricontrolla domani a mercato chiuso.")
        st.markdown('<div class="sezione">Cosa fare adesso</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="card"><div class="txt">{html_testo(cosa)}</div></div>', unsafe_allow_html=True)
        with st.expander("📘 Esercizio: i numeri se oggi fosse verde"):
            st.caption("Solo per imparare a leggere il riquadro. **Oggi non è un'operazione da fare.**")
            passi_operativi(p, v, nome, valuta, cambio, rischio, spiegazione_stop)

    st.markdown('<div class="nota" style="margin-top:18px">Scopo didattico, non è consulenza finanziaria. '
                'Gli ordini li inserisci tu, sul conto demo.</div>', unsafe_allow_html=True)


# ==============================================================================
# SEZIONE PIANO: il piano personale costruito sulle tue risposte
# ==============================================================================
def schermata_piano():
    P = PIANO
    cap = ss.capitale
    st.markdown('<div class="titolo">Il mio piano</div>'
                '<div class="sottotit">Costruito sulle tue risposte. L\'assistente e la sentinella lo seguono.</div>',
                unsafe_allow_html=True)

    prof = P.get("profilo", {})
    righe = "".join(f"<span>{k}</span><span>{v}</span>" for k, v in
                    [("Tempo", prof.get("tempo", "")), ("Rischio", prof.get("rischio", "")),
                     ("Obiettivo", prof.get("obiettivo", "")), ("Ordini", prof.get("esecuzione", ""))])
    st.markdown(f'<div class="card"><div class="tit" style="font-weight:700">👤 Chi sei</div>'
                f'<div class="campi" style="grid-template-columns:auto 1fr">{righe}</div></div>',
                unsafe_allow_html=True)

    r, rc = ss.rischio, P.get("rischio_cripto", ss.rischio)
    voci = [
        ("Rischio per operazione", f"{fmt_pct(r)}%", f"max {fmt_num(cap * r / 100, 0)} € a operazione"),
        ("Rischio sulle cripto", f"{fmt_pct(min(r, rc))}%", "sono più nervose: si rischia meno"),
        ("Operazioni aperte", f"max {P.get('max_posizioni_aperte', 3)}", "mai tutte le uova in un paniere"),
        ("Stop del giorno", f"−{P.get('stop_giornaliero_pct', 2)}%",
         f"a −{fmt_num(cap * P.get('stop_giornaliero_pct', 2) / 100, 0)} € si chiude per oggi"),
        ("Stop della settimana", f"−{P.get('stop_settimanale_pct', 4)}%",
         f"a −{fmt_num(cap * P.get('stop_settimanale_pct', 4) / 100, 0)} € pausa fino a lunedì"),
        ("Stop del mese", f"−{P.get('stop_mensile_pct', 8)}%", "sotto il tuo limite del −10%: si ripassa il piano"),
    ]
    st.markdown('<div class="sezione">Le tue regole</div>', unsafe_allow_html=True)
    st.markdown('<div class="tiles" style="grid-template-columns:repeat(2,1fr)">' + "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
        for k, val, s in voci) + "</div>", unsafe_allow_html=True)
    dalle, alle = P.get("orari_avvisi", ["00:00", "23:59"])
    st.markdown(f'<div class="nota">🔔 Avvisi su Telegram dalle {dalle} alle {alle}: di notte la sentinella controlla '
                'ma non ti sveglia, e ti aggiorna al mattino.</div>', unsafe_allow_html=True)

    ob = float(P.get("obiettivo", 0) or 0)
    if ob > cap and P.get("palestra"):
        st.markdown('<div class="sezione">🎯 L\'obiettivo del bot sul Demo</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="card"><div class="tit" style="font-weight:800;font-size:1.15rem">'
            f'{fmt_num(cap, 0)} € → {fmt_num(ob, 0)} € (+{(ob / cap - 1) * 100:.0f}%)</div>'
            '<div class="txt">Modalità <b>Palestra</b>: sul conto Demo il bot opera con capitale e rischio pieni per studiare '
            'il mercato dal vivo. Sono soldi finti: serve a capire se le regole funzionano davvero, fuori dal backtest. '
            'L\'avanzamento lo vedi nella sezione <b>Bot</b> e su Telegram (/stato).</div>'
            '<div class="txt" style="margin-top:8px">Il tuo piano per il <b>conto vero</b> resta prudente: si parte piccoli, '
            'con rischio dimezzato, solo dopo che il Demo avrà dato risultati positivi su almeno 30-40 operazioni.</div></div>',
            unsafe_allow_html=True)
    elif ob > cap:
        st.markdown('<div class="sezione">🎯 Il tuo obiettivo</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="card"><div class="tit" style="font-weight:800;font-size:1.15rem">'
            f'{fmt_num(cap, 0)} € → {fmt_num(ob, 0)} €</div>'
            '<div class="txt">L\'avanzamento lo vedi nella sezione <b>Bot</b> e su Telegram (/stato). '
            'Con i costi reali inclusi, la ricerca attuale <b>non trova un vantaggio affidabile</b> nelle regole provate: '
            'oggi il trading da solo non avvicina l\'obiettivo, e il bot per questo non opera finché la ricerca non trova '
            'una regola valida.</div>'
            '<div class="campi" style="grid-template-columns:auto 1fr">'
            '<span>+50 € risparmiati al mese</span><span><b>circa 10 mesi</b></span>'
            '<span>+100 € risparmiati al mese</span><span><b>circa 5 mesi</b></span>'
            '</div><div class="txt" style="margin-top:8px">La strada concreta per raddoppiare è <b>aggiungere risparmi</b>; '
            'il bot contribuirà solo se e quando la sua ricerca dimostrerà un vantaggio reale.</div></div>',
            unsafe_allow_html=True)

    st.markdown('<div class="sezione">Il tuo percorso</div>', unsafe_allow_html=True)
    fase = P.get("fase", 1)
    for i, f in enumerate(P.get("fasi", []), start=1):
        qui = i == fase
        stile = f'border:1.5px solid {T["ema"]};' if qui else ("opacity:.75;" if i > fase else "")
        badge = (f'<span style="background:{T["ema"]};color:#fff;border-radius:999px;padding:2px 9px;'
                 f'font-size:.7rem;font-weight:800;margin-left:6px">SEI QUI</span>') if qui else ""
        st.markdown(
            f'<div class="passo" style="{stile}"><div class="num" style="border-color:{T["ema"]};color:{T["ema"]};'
            f'background:{T["ema"]}1a">{i}</div><div style="flex:1">'
            f'<div class="tit">{f["nome"]}{badge}</div><div class="nota" style="margin:0 0 4px">{f["durata"]}</div>'
            f'<div class="txt">{f["cosa"]}</div>'
            f'<div class="txt" style="margin-top:6px">🎯 <b>Traguardo:</b> {f["traguardo"]}</div></div></div>',
            unsafe_allow_html=True)

    buono, ottimo = cap * 0.02, cap * 0.04
    st.markdown('<div class="sezione">Aspettative oneste</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="card"><div class="txt">Con <b>{fmt_num(cap, 0)} €</b> e rischio {fmt_pct(r)}%, un mese '
        f'<b>buono</b> per chi è bravo vale circa <b>+{fmt_num(buono, 0)} / +{fmt_num(ottimo, 0)} €</b> (+2/4%), '
        'e ci saranno anche mesi negativi. Un\'entrata extra vera arriva <b>col tempo</b>: prima si dimostra di '
        'saper guadagnare in modo costante, poi cresce il capitale, non il rischio.<br><br>'
        '🚫 La tentazione da evitare: aumentare leva o quantità per “fare prima”. È il modo più veloce '
        'per svuotare un conto.</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="nota">Vuoi cambiare qualcosa del piano? Dimmelo e lo aggiorno (sta nel file piano.json).</div>',
                unsafe_allow_html=True)


# ==============================================================================
# SEZIONE BOT: il diario del bot (letto dalla sua memoria sul branch "dati")
# ==============================================================================
URL_MEMORIA = "https://raw.githubusercontent.com/mazzierialessandro99-wq/tutor-trading/dati/stato_sentinella.json"


@st.cache_data(ttl=120, show_spinner=False)
def memoria_bot(nome_file: str = "stato_sentinella.json") -> dict | None:
    import json
    import urllib.request
    locale = os.environ.get("MEMORIA_BOT_DIR")      # solo per le prove dello sviluppatore
    try:
        if locale:
            return json.loads(open(os.path.join(locale, nome_file), encoding="utf-8").read())
        with urllib.request.urlopen(URL_MEMORIA.replace("stato_sentinella.json", nome_file), timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def riquadro_ricerca():
    ric = memoria_bot("ricerca_esito.json")
    st.markdown('<div class="sezione">🔬 Cosa ha deciso la ricerca</div>', unsafe_allow_html=True)
    if not ric:
        st.markdown('<div class="card"><div class="txt">La ricerca settimanale non è ancora disponibile. '
                    'Finché non c\'è, il bot non apre operazioni.</div></div>', unsafe_allow_html=True)
        return
    data = pd.Timestamp(ric["data"]).strftime("%d/%m/%Y")
    v = ric.get("vincitrice")
    if v:
        nomi_s = {"ritracciamento": "ritracciamento in trend (EMA 200 + RSI)", "rottura": "rottura dei massimi a 55 giorni"}
        testo = (f"<b>Opera</b> con la strategia <b>{nomi_s.get(v['strategia'], v['strategia'])}</b>, take profit 1:{v['rr']:.0f}"
                 f"{', stop a pareggio' if v.get('pareggio') else ''}, filtro <b>{v['filtro']}</b>. Sui mercati mai visti: "
                 f"profit factor {v['mai_visti']['profit_factor']:.2f}, risultato {v['mai_visti']['rendimento_pct']:+.1f}%.")
        colore = "VERDE"
    else:
        testo = ("<b>Nessuna regola promossa.</b> Con i costi reali (spread e commissioni notturne) nessuna delle "
                 f"{len(ric.get('configurazioni', []))} combinazioni provate ha un vantaggio affidabile anche sui mercati mai visti. "
                 "La ricerca si ripete ogni domenica: quando una regola supererà il test, il bot userà quella.")
        if PIANO.get("palestra"):
            testo += (" <br><br>🧪 <b>Modalità Palestra attiva:</b> sul Demo il bot opera comunque la strategia di base, "
                      "per raccogliere risultati veri. Su un conto reale non lo farebbe.")
        colore = "GIALLO"
    st.markdown(f'<div class="card" style="border-color:{STATO[colore]}77"><div class="txt">{testo}</div>'
                f'<div class="nota" style="margin:6px 0 0">Ricerca del {data} · regola: {ric.get("regola", "")}</div></div>',
                unsafe_allow_html=True)
    conf = ric.get("configurazioni") or []
    if conf:
        with st.expander("📊 Tutte le combinazioni provate"):
            st.dataframe(pd.DataFrame([{
                "Strategia": c["strategia"], "TP": f"1:{c['rr']:.0f}", "Pareggio": "sì" if c["pareggio"] else "no",
                "Quando": c["filtro"], "PF 20 mercati": c["base"]["profit_factor"],
                "PF mai visti": c["mai_visti"]["profit_factor"], "Risultato mai visti %": c["mai_visti"]["rendimento_pct"],
                "Promossa": "✅" if c["promossa"] else ""} for c in conf]), hide_index=True, width="stretch")


def schermata_bot():
    m = memoria_bot()
    if not m:
        st.markdown('<div class="titolo">Il mio bot</div>', unsafe_allow_html=True)
        st.markdown('<div class="card"><div class="txt">Il diario non è ancora disponibile: compare dopo il primo giro del '
                    'motore. Riprova tra 30 minuti.</div></div>', unsafe_allow_html=True)
        return
    ric = memoria_bot("ricerca_esito.json")
    adesso = pd.Timestamp.now(tz="Europe/Rome")
    ultimo = pd.Timestamp(m["ultimo_giro"]) if m.get("ultimo_giro") else None
    minuti = (adesso - ultimo).total_seconds() / 60 if ultimo is not None else None
    fresco = minuti is not None and minuti <= 75
    quando = "mai" if minuti is None else f"{minuti:.0f} min fa" if minuti < 120 else f"{minuti / 60:.0f} ore fa"
    sett = adesso.isocalendar()
    giri = (m.get("giri") or {}).get(f"{sett[0]}-W{sett[1]:02d}", 0)
    decisioni = m.get("decisioni") or []
    oggi = [d for d in decisioni if str(d.get("ora", ""))[:10] == adesso.strftime("%Y-%m-%d")]
    visti = sum("Semaforo" in d["decisione"] or "Segnale" in d["decisione"] or "aperta" in d["decisione"] for d in oggi)
    aperte_oggi = sum(d["decisione"] == "Operazione aperta" for d in oggi)
    cfg = (ric or {}).get("vincitrice")

    # ---- stato e racconto della giornata ----
    if not fresco:
        stato_t, colore, frase = "Fermo?", "ROSSO", ("Non do notizie da più di un'ora: il motore potrebbe essersi fermato. "
                                                     "Se non riparte entro qualche ora, scrivimelo in chat.")
    elif m.get("modalita") == "pausa":
        stato_t, colore, frase = "In pausa", "GIALLO", "Mi hai messo in pausa: guardo i mercati ma non apro operazioni. Scrivi /riprendi su Telegram per farmi ripartire."
    elif m.get("modalita") == "automatica" and not cfg and PIANO.get("palestra"):
        stato_t, colore = "Palestra sul Demo", "VERDE"
        frase = ("Sul Demo opero i segnali della strategia di base <b>anche se la ricerca non la promuove</b>: ogni operazione "
                 "è un esperimento per studiare il mercato dal vivo e confrontarlo con il backtest. "
                 f"Oggi: {visti} segnali visti, {aperte_oggi} operazioni aperte.")
    elif m.get("modalita") == "automatica" and not cfg:
        stato_t, colore = "Osservo e studio", "GIALLO"
        frase = ("Oggi guardo i mercati <b>senza operare</b>: la mia ricerca dice che, con i costi reali, nessuna regola ha "
                 "un vantaggio affidabile. " + (f"Ho visto {visti} segnali, li tengo come studio." if visti else
                                                 "Per ora nessun segnale interessante.") + " Domenica rifaccio la ricerca.")
    elif m.get("modalita") == "automatica":
        stato_t, colore = "Opero sul Demo", "VERDE"
        frase = (f"Sto operando con la regola promossa dalla ricerca. Oggi: {visti} segnali visti, "
                 f"{aperte_oggi} operazioni aperte.")
    else:
        stato_t, colore, frase = "Solo avvisi", "GIALLO", "Ti mando gli avvisi su Telegram, gli ordini li metti tu."
    st.markdown(
        f'<div class="bot-hero"><div class="bot-av">🤖</div><div style="flex:1">'
        f'<div class="bot-nome">Il tuo bot <span class="bot-stato" style="background:{STATO[colore]}22;color:{STATO_TESTO[colore]};'
        f'border-color:{STATO[colore]}66">● {stato_t}</span></div>'
        f'<div class="bot-frase">{frase}</div>'
        f'<div class="bot-meta">Ultimo controllo {quando} · {giri} controlli questa settimana · ogni 30 minuti</div>'
        f'</div></div>', unsafe_allow_html=True)

    riquadro_ricerca()

    # ---- obiettivo e numeri ----
    storia = m.get("storia") or []
    cap0 = float(m.get("capitale_piano") or PIANO.get("capitale", 500))
    ob = float(m.get("obiettivo") or PIANO.get("obiettivo", 0) or 0)
    attuale = float(storia[-1][1]) if storia else cap0
    chiuse = m.get("chiuse") or []
    st_ = sentinella.statistiche(chiuse)
    quota = max(0.0, min(1.0, (attuale - cap0) / (ob - cap0))) if ob > cap0 else 0.0
    st.markdown('<div class="sezione">🎯 Verso l\'obiettivo</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'<div class="tit" style="font-weight:800;font-size:1.2rem">{fmt_num(attuale, 2)} €</div>'
        f'<div class="nota" style="margin:0">obiettivo {fmt_num(ob, 0)} €</div></div>'
        f'<div style="height:12px;border-radius:999px;background:var(--surf2);margin:10px 0 4px;overflow:hidden">'
        f'<div style="width:{max(quota * 100, 1.5):.1f}%;height:100%;background:{T["ema"]};border-radius:999px"></div></div>'
        f'<div class="nota" style="margin:0">Partenza {fmt_num(cap0, 0)} € · {quota * 100:.0f}% del percorso</div></div>',
        unsafe_allow_html=True)
    risultato = attuale - cap0
    voci = [("Risultato del bot", f"{'+' if risultato >= 0 else '−'}{fmt_num(abs(risultato))} €", "dall'inizio del piano"),
            ("Operazioni chiuse", str(st_["n"]), f"{len(m.get('posizioni') or [])} ancora aperte"),
            ("Vinte", f"{st_['win_rate']:.0f}%" if st_["n"] else "—", "atteso circa 40%"),
            ("Per giudicare", f"{st_['n']}/30", "operazioni chiuse")]
    st.markdown('<div class="tiles" style="grid-template-columns:repeat(2,1fr)">' + "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
        for k, val, s in voci) + "</div>", unsafe_allow_html=True)
    if len(storia) >= 2:
        df = pd.DataFrame(storia, columns=["quando", "capitale"])
        df["quando"] = pd.to_datetime(df["quando"], utc=True).dt.tz_convert("Europe/Rome")
        fig = go.Figure(go.Scatter(x=df["quando"], y=df["capitale"], mode="lines", line=dict(color=T["ema"], width=2.2, shape="hv"),
                                   hovertemplate="%{y:,.2f} €<extra></extra>"))
        fig.add_hline(y=cap0, line=dict(color=T["muto"], width=1, dash="dot"))
        lo, hi = df["capitale"].min(), df["capitale"].max()
        pad = max((hi - lo) * 0.2, cap0 * 0.004)
        fig.update_layout(height=220, template="plotly_dark" if SCURO else "plotly_white", showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                          margin=dict(l=4, r=4, t=8, b=4), hovermode="x unified", font=dict(color=T["testo2"], size=11))
        fig.update_xaxes(gridcolor=T["griglia"], tickformat="%d/%m", hoverformat="%d/%m %H:%M")
        fig.update_yaxes(gridcolor=T["griglia"], side="right", range=[min(lo, cap0) - pad, max(hi, cap0) + pad])
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ---- posizioni aperte ----
    pos = m.get("posizioni") or []
    st.markdown(f'<div class="sezione">📂 Operazioni aperte ({len(pos)})</div>', unsafe_allow_html=True)
    if not pos:
        st.markdown('<div class="nota">Nessuna operazione aperta in questo momento.</div>', unsafe_allow_html=True)
    for p in pos:
        upl = float(p.get("upl") or 0)
        livello, stop_, tp_ = (float(p.get(k) or 0) for k in ("livello", "stop", "tp"))
        corrente = float(p["bid"]) if p.get("bid") else livello
        quota_pos = max(0.0, min(1.0, (corrente - stop_) / (tp_ - stop_))) if tp_ > stop_ else 0.5
        st.markdown(
            f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div class="tit" style="font-weight:700">{p.get("nome")}</div>'
            f'<div style="font-weight:800;color:{T["su"] if upl >= 0 else T["giu"]}">{"+" if upl >= 0 else "−"}{fmt_num(abs(upl))} €</div></div>'
            f'<div class="nota" style="margin:2px 0 8px">{fmt_quote(float(p.get("size") or 0))} contratti a {fmt_prezzo(livello)}</div>'
            f'<div style="position:relative;height:8px;border-radius:999px;background:linear-gradient(90deg,{T["giu"]}55,var(--surf2) 33%,var(--surf2) 34%,{T["su"]}55)">'
            f'<div style="position:absolute;left:calc({quota_pos * 100:.0f}% - 6px);top:-3px;width:14px;height:14px;border-radius:50%;'
            f'background:{T["testo"]};border:2px solid var(--surf)"></div></div>'
            f'<div style="display:flex;justify-content:space-between;margin-top:6px" class="nota">'
            f'<span>stop {fmt_prezzo(stop_)}</span><span>take profit {fmt_prezzo(tp_)}</span></div></div>',
            unsafe_allow_html=True)

    # ---- diario delle decisioni ----
    st.markdown('<div class="sezione">🗒️ Cosa ho fatto e perché</div>', unsafe_allow_html=True)
    if not decisioni:
        st.markdown('<div class="nota">Qui comparirà ogni mia decisione: segnali visti, operazioni aperte o saltate, e il motivo.</div>',
                    unsafe_allow_html=True)
    else:
        righe, giorno_prec = [], None
        for d in reversed(decisioni[-40:]):
            t = pd.Timestamp(d["ora"])
            giorno = ("Oggi" if t.date() == adesso.date() else "Ieri" if t.date() == (adesso - pd.Timedelta(days=1)).date()
                      else t.strftime("%d/%m"))
            if giorno != giorno_prec:
                righe.append(f'<div class="tl-giorno">{giorno}</div>')
                giorno_prec = giorno
            righe.append(f'<div class="tl-voce"><div class="tl-ora">{t.strftime("%H:%M")}</div><div class="tl-ico">{d.get("icona", "•")}</div>'
                         f'<div><div class="tl-tit"><b>{d["mercato"]}</b> · {d["decisione"]}</div>'
                         f'<div class="tl-mot">{d["motivo"]}</div></div></div>')
        st.markdown('<div class="card tl">' + "".join(righe) + "</div>", unsafe_allow_html=True)

    # ---- operazioni chiuse ----
    if chiuse:
        st.markdown('<div class="sezione">🏁 Operazioni chiuse</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{
            "": "✅" if (c.get("euro") or 0) > 0 else "❌", "Mercato": c.get("nome"),
            "Aperta": pd.Timestamp(c["aperta"]).strftime("%d/%m/%y") if c.get("aperta") else "",
            "Chiusa": pd.Timestamp(c["chiusa"]).strftime("%d/%m/%y") if c.get("chiusa") else "",
            "Risultato": (f"{'+' if c['euro'] >= 0 else '−'}{fmt_num(abs(float(c['euro'])))} €" if c.get("euro") is not None else "n.d.")}
            for c in reversed(chiuse)]), hide_index=True, width="stretch")
    st.markdown('<div class="nota" style="margin-top:14px">Comandi su Telegram: /stato · /resoconto · /stop · /riprendi.</div>',
                unsafe_allow_html=True)


# ==============================================================================
# SEZIONE IMPARA
# ==============================================================================
def schermata_impara():
    st.markdown('<div class="titolo">Perché e regole d\'oro</div>'
                '<div class="sottotit">Leggile prima di guardare i segnali: sono le regole che ti tengono in gioco.</div>',
                unsafe_allow_html=True)

    with st.expander("1️⃣  Perché non esiste “rischio zero, guadagno massimo”", expanded=True):
        st.markdown(
            """
Nei mercati **nessuno sa cosa farà il prezzo domani**. Neanche le banche, neanche gli algoritmi.
Ogni strategia ha operazioni vincenti e operazioni perdenti: chi promette guadagni sicuri
ti sta vendendo qualcosa.

Rischio e rendimento vanno **sempre insieme**: per poter guadagnare devi accettare di poter perdere.
La differenza tra chi sopravvive e chi brucia il conto non è indovinare sempre,
ma **perdere poco quando sbagli**. Questa si chiama **gestione del rischio**.
"""
        )
        st.markdown("**Perché le perdite grandi sono così pericolose:** per recuperarle serve molto di più.")
        perdite = [10, 20, 30, 50, 75, 90]
        st.dataframe(pd.DataFrame({
            "Se perdi": [f"−{p}%" for p in perdite],
            "Per tornare in pari ti serve": [f"+{p / (100 - p) * 100:.0f}%" for p in perdite],
        }), hide_index=True, width="stretch")
        st.info("Perdere il 50% significa dover poi **raddoppiare** il capitale solo per tornare al punto di partenza.")

    with st.expander("2️⃣  Gli indicatori: EMA 200, RSI, ATR"):
        st.markdown(
            f"""
Un indicatore è un **calcolo fatto sui prezzi passati** che ci aiuta a leggere il grafico.
Non predice il futuro: ci dà un quadro ordinato della situazione.

- **EMA 200 → il trend.** È la media dei prezzi degli ultimi 200 giorni circa. Prezzo **sopra** = trend positivo;
  **sotto** = trend negativo, e non compriamo.
- **RSI (14) → il momento.** Va da 0 a 100. Tra **{L.RSI_MIN} e {L.RSI_MAX}** il prezzo ha fatto una pausa:
  possibile occasione *se il trend è positivo*. Sopra **{L.RSI_TIRATO}** è “tirato”: meglio non inseguirlo.
- **ATR (14) → la volatilità.** È quanto si muove in media in una giornata. Ci dice **quanto largo
  mettere lo stop** per non farci buttare fuori dal rumore.
"""
        )
        st.markdown("**Esempio** (prezzi inventati): il prezzo sta sopra la sua EMA 200, quindi il trend è positivo.")
        rng = np.random.default_rng(7)
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0008, 0.012, 400))))
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=s, name="Prezzo", line=dict(width=1.5, color=T["testo2"])))
        fig.add_trace(go.Scatter(y=s.ewm(span=200, adjust=False).mean(), name="EMA 200",
                                 line=dict(width=2.5, color=T["ema"])))
        fig.update_layout(height=240, margin=dict(l=4, r=4, t=8, b=4),
                          template="plotly_dark" if SCURO else "plotly_white",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=1.14), hovermode="x unified",
                          font=dict(color=T["testo2"]))
        fig.update_xaxes(gridcolor=T["griglia"], title="giorni")
        fig.update_yaxes(gridcolor=T["griglia"])
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with st.expander("3️⃣  Stop Loss, Take Profit e la regola dell'1%"):
        st.markdown(
            """
- **Stop Loss (SL)**: il prezzo a cui l'operazione si **chiude da sola in perdita**.
  Lo decidi *prima* di entrare, a mente fredda. È la tua cintura di sicurezza.
- **Take Profit (TP)**: il prezzo a cui l'operazione si **chiude da sola in guadagno**.
- **Rapporto 1:2**: il TP è lontano dall'entrata **il doppio** dello SL.
  Così anche vincendo solo **4 operazioni su 10** il conto può restare in attivo.

**La regola dell'1%:** su una singola operazione non rischi mai più dell'**1% del capitale**.
Con 1.000 € significa al massimo **10 €** di perdita se tocca lo stop.
Anche 10 perdite di fila (capita!) ti lasciano circa il 90% del capitale.

La quantità da comprare **non si sceglie a sentimento**, si calcola:
"""
        )
        st.latex(r"\text{quote} = \frac{\text{capitale} \times 1\%}{\text{prezzo di entrata} - \text{stop loss}}")
        st.markdown("**Prova tu:**")
        with st.container(horizontal=True):
            entrata = st.number_input("Prezzo di entrata", min_value=0.01, value=50.0, step=0.5, key="t1_in")
            stop = st.number_input("Stop Loss", min_value=0.01, value=48.0, step=0.5, key="t1_sl")
        cap, rischio = ss.capitale, ss.rischio
        if stop >= entrata:
            st.error("Per un acquisto lo Stop Loss deve stare **sotto** il prezzo di entrata.")
        else:
            dist = entrata - stop
            quote = min(cap * rischio / 100 / dist, cap / entrata)
            st.success(
                f"Con il tuo capitale di **{fmt_num(cap, 0)} €** e rischio **{fmt_pct(rischio)}%**: compri "
                f"**{fmt_quote(quote)} quote** a **{fmt_prezzo(entrata)}** (impegni {fmt_num(quote * entrata, 0)} €), "
                f"Stop Loss **{fmt_prezzo(stop)}**, Take Profit **{fmt_prezzo(entrata + 2 * dist)}**. "
                f"Se va male perdi circa **{fmt_num(quote * dist)} €**, se va bene guadagni circa **{fmt_num(quote * dist * 2)} €**."
            )
            st.caption("Capitale e rischio si cambiano dal pulsante 💶 in alto. Se il broker non vende quote frazionarie, "
                       "arrotonda **per difetto**.")

    with st.expander("4️⃣  Dove mettere lo stop loss (e dove no)"):
        st.markdown(
            """
Lo stop loss è la decisione più importante di ogni operazione: dice **quando l'idea era sbagliata**.

**Tre modi di metterlo** (li trovi calcolati su ogni mercato in *Segnali → tocca un mercato → Il tuo tutor*):
- **Sotto il minimo recente**, con un piccolo margine. Ha un significato preciso: se il prezzo rompe il minimo
  da cui doveva ripartire, la pausa è diventata una discesa. È il metodo preferito quando il minimo è a una
  distanza sensata (tra 1,5 e 3,5 volte l'ATR).
- **In base alla volatilità** (2 volte l'ATR, 2,5 se il mercato è agitato). Si adatta a quanto si muove quel mercato:
  le oscillazioni normali non lo toccano.
- **A percentuale fissa** (es. −3%). Comodo, ma cieco: su un mercato calmo è troppo largo, su uno agitato troppo stretto.

**Le regole che valgono sempre:**
1. Lo stop si decide **prima** di entrare e si imposta **insieme** all'ordine.
2. **Mai troppo stretto**: sotto 1 ATR viene toccato dal rumore di una sola giornata.
3. **Non esattamente sul minimo**: lì si accumulano gli stop di tutti. Meglio un po' sotto.
4. **Mai allontanarlo** dopo essere entrato "per dargli spazio": è il modo più rapido per trasformare una piccola perdita in una grande.
5. **Avvicinarlo** è ammesso solo con una regola decisa prima (per esempio a pareggio quando guadagni quanto rischiavi).
6. **La quantità viene dallo stop**, non il contrario: stop più lontano = meno quote, così il rischio in euro resta l'1%.
"""
        )

    with st.expander("5️⃣  Le regole d'oro in una schermata"):
        st.markdown(
            """
1. **Prima la demo.** Almeno 2-3 mesi e 30+ operazioni su conto demo prima di pensare a soldi veri.
2. **Mai più dell'1%** del capitale a rischio su una singola operazione.
3. **Stop Loss sempre**, impostato *nello stesso momento* in cui apri l'operazione. Mai spostarlo per “dare più spazio”.
4. **Solo a favore del trend**: se il semaforo è rosso, non si opera. Punto.
5. **Niente vendetta**: dopo 3 perdite di fila, stop per la giornata.
6. **Tieni un diario**: data, asset, perché sei entrato, com'è finita. È così che si impara.
7. **Questa app è un tutor, non un oracolo.** I segnali possono sbagliare: per questo esiste lo stop.
"""
        )
    st.markdown('<div class="nota">Scopo didattico, non è consulenza finanziaria.</div>', unsafe_allow_html=True)


# ==============================================================================
# SEZIONE TEST (backtest)
# ==============================================================================
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def calcola_backtest(capitale: float) -> dict:
    B = backtest
    tickers = [t for t, _ in L.ASSET.values()]
    if DEMO:
        dati = {t: _dati_demo(t) for t in tickers}
    else:
        dati = sentinella.scarica_tutti(tickers, periodo="5y")
    r = B.esegui(dati, capitale, PIANO)
    r["mercati"] = len(dati)
    return r


def schermata_test():
    B = backtest
    st.markdown('<div class="titolo">Verifica sul passato</div>'
                '<div class="sottotit">Le stesse regole del semaforo e del tuo piano, provate sugli ultimi 3 anni '
                'di 20 mercati. Come se l\'assistente fosse stato acceso dal 2023.</div>', unsafe_allow_html=True)

    with st.expander("ℹ️ Come funziona la verifica"):
        st.markdown(
            f"""
- Ogni volta che in passato un semaforo **è diventato verde**, si compra all'apertura del giorno dopo.
- Stop-loss a **{fmt_num(L.STOP_ATR, 0)} ATR** sotto, Take profit a **{fmt_num(L.STOP_ATR * L.RR, 0)} ATR** sopra (1:{fmt_num(L.RR, 0)}).
- Rischio del tuo piano: **{fmt_pct(PIANO.get('rischio_per_operazione', 1))}%** ({fmt_pct(PIANO.get('rischio_cripto', 0.5))}% sulle cripto),
  massimo **{PIANO.get('max_posizioni_aperte', 3)}** operazioni aperte insieme.
- Se nello stesso giorno vengono toccati stop e take profit, contiamo lo **stop** (ipotesi prudente).
- Costi di spread e commissioni stimati allo **0,1%** per operazione.
"""
        )

    if st.button("▶️  Esegui la verifica", type="primary", width="stretch", key="esegui_bt"):
        ss.bt_fatto = True
    if not ss.get("bt_fatto"):
        st.markdown('<div class="nota">Ci vogliono circa 20-30 secondi: scarico 5 anni di prezzi per 20 mercati.</div>',
                    unsafe_allow_html=True)
        return

    with st.spinner("Rigioco 3 anni di mercati…"):
        try:
            r = calcola_backtest(float(PIANO.get("capitale", 1000)))
        except Exception:
            r = {"n": 0}
    if not r.get("n"):
        st.error("Non sono riuscito a completare la verifica (dati non disponibili). Riprova tra qualche minuto.")
        return

    cap = float(PIANO.get("capitale", 1000))
    giudizio, spiegazione = B.verdetto(r)
    colore = {"buono": "VERDE", "debole": "GIALLO", "negativo": "ROSSO"}[giudizio]
    titolo = {"buono": "Le regole reggono", "debole": "Risultato debole", "negativo": "Le regole perdono"}[giudizio]
    st.markdown(
        f'<div class="sem" style="border-color:{STATO[colore]}55;background:linear-gradient(135deg,{STATO[colore]}26,var(--surf) 72%)">'
        f'<div style="font-size:2.2rem">{"✅" if giudizio == "buono" else "⚠️" if giudizio == "debole" else "⛔"}</div>'
        f'<div><div class="sem-colore" style="color:{STATO_TESTO[colore]};font-size:1.35rem">{titolo}</div>'
        f'<div class="sem-txt">{spiegazione}</div>'
        f'<div class="sem-meta">{r["curva"].index[0]:%d/%m/%Y} → {r["curva"].index[-1]:%d/%m/%Y} · {r["mercati"]} mercati · '
        f'{r["n"]} operazioni chiuse</div></div></div>', unsafe_allow_html=True)

    voci = [("Capitale finale", f"{fmt_num(r['finale'], 0)} €", f"partendo da {fmt_num(cap, 0)} €"),
            ("Rendimento", f"{'+' if r['rendimento_pct'] >= 0 else '−'}{fmt_num(abs(r['rendimento_pct']), 1)}%",
             f"{'+' if r['annuo_pct'] >= 0 else '−'}{fmt_num(abs(r['annuo_pct']), 1)}% all'anno"),
            ("Win rate", f"{fmt_num(r['win_rate'], 0)}%", "operazioni chiuse in guadagno"),
            ("Drawdown massimo", f"−{fmt_num(abs(r['max_dd_pct']), 1)}%", "la discesa peggiore dal picco")]
    st.markdown('<div class="tiles" style="grid-template-columns:repeat(2,1fr)">' + "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
        for k, val, s in voci) + "</div>", unsafe_allow_html=True)

    # ---- curva del capitale ----
    st.markdown('<div class="sezione">Come sarebbe andato il capitale</div>', unsafe_allow_html=True)
    curva, dd = r["curva"], r["drawdown"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.72, 0.28],
                        subplot_titles=("Capitale (€)", "Drawdown (%) · quanto sei sotto il massimo"))
    fig.add_trace(go.Scatter(x=curva.index, y=curva.values, mode="lines", line=dict(color=T["ema"], width=2.2, shape="hv"),
                             name="Capitale", hovertemplate="%{y:,.2f} €<extra></extra>"), row=1, col=1)
    fig.add_hline(y=cap, line=dict(color=T["muto"], width=1, dash="dot"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines", fill="tozeroy", line=dict(color=T["giu"], width=1.5, shape="hv"),
                             fillcolor=T["giu"] + "33", name="Drawdown", hovertemplate="%{y:.1f}%<extra></extra>"), row=2, col=1)
    fig.update_layout(height=430, template="plotly_dark" if SCURO else "plotly_white", showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      margin=dict(l=4, r=4, t=28, b=4), hovermode="x unified", font=dict(color=T["testo2"], size=12))
    fig.update_xaxes(gridcolor=T["griglia"], tickformat="%m/%y", hoverformat="%d/%m/%Y")
    fig.update_yaxes(gridcolor=T["griglia"], side="right", zeroline=False)
    fig.update_annotations(font=dict(size=12, color=T["muto"]), x=0, xanchor="left")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ---- spiegazioni con i numeri veri ----
    st.markdown('<div class="sezione">Cosa significano questi numeri</div>', unsafe_allow_html=True)
    spiegazioni = [
        ("🎯", "Win rate", f"Su 10 operazioni, circa <b>{fmt_num(r['win_rate'] / 10, 0)}</b> sono finite in guadagno. "
         f"Non serve vincere spesso: con il rapporto 1:2 una vincita media (<b>{fmt_num(r['media_vinta'])} €</b>) "
         f"vale circa il doppio di una perdita media (<b>{fmt_num(abs(r['media_persa']))} €</b>). Il punto di pareggio è circa il 34%."),
        ("📉", "Drawdown massimo", f"Nel momento peggiore il conto era <b>{fmt_num(abs(r['max_dd_pct']), 1)}%</b> sotto il suo "
         f"massimo precedente, cioè circa <b>{fmt_num(cap * abs(r['max_dd_pct']) / 100, 0)} €</b> su {fmt_num(cap, 0)}. "
         "È la discesa che devi essere pronto a sopportare senza mollare il piano."),
        ("⚖️", "Profit factor", f"Per ogni euro perso se ne sono guadagnati <b>{fmt_num(r['profit_factor'], 2)}</b>. "
         "Sopra 1 la strategia guadagna; sopra 1,3 è considerata solida."),
        ("🔁", "Perdite di fila", f"La serie peggiore è stata di <b>{r['perdite_di_fila']}</b> operazioni perse una dopo l'altra. "
         "Capiterà anche dal vivo: è normale e non vuol dire che le regole siano rotte."),
    ]
    for ico, tit, txt in spiegazioni:
        st.markdown(f'<div class="card spia"><div class="ico">{ico}</div><div><div class="tit">{tit}</div>'
                    f'<div class="txt">{txt}</div></div></div>', unsafe_allow_html=True)

    # ---- dettagli ----
    with st.expander("📊 Risultato per mercato"):
        pm = r["per_mercato"].rename(columns={"mercato": "Mercato", "operazioni": "Operazioni", "euro": "Risultato €",
                                              "vinte": "Vinte %"})
        st.dataframe(pm, hide_index=True, width="stretch",
                     column_config={"Risultato €": st.column_config.NumberColumn(format="%.2f"),
                                    "Vinte %": st.column_config.NumberColumn(format="%.0f")})
    with st.expander("🧾 Ultime 20 operazioni"):
        op = r["operazioni"].sort_values("entrata", ascending=False).head(20)
        st.dataframe(pd.DataFrame({"Mercato": op["mercato"], "Entrata": op["entrata"].dt.strftime("%d/%m/%y"),
                                   "Uscita": op["uscita"].dt.strftime("%d/%m/%y"), "Esito": op["esito"],
                                   "€": op["euro"].round(2)}), hide_index=True, width="stretch")

    st.markdown('<div class="card"><div class="txt">⚠️ <b>Onestà prima di tutto:</b> il passato non garantisce il futuro. '
                'I dati di Yahoo sono indicativi, spread e slippage reali possono essere più alti, e i mercati cambiano. '
                'Per questo il piano prevede settimane di prova sul <b>Demo</b> prima di usare soldi veri.</div></div>',
                unsafe_allow_html=True)


# ==============================================================================
# INSTRADAMENTO
# ==============================================================================
if pagina == PAGINE[0]:
    schermata_bot()
elif pagina == PAGINE[1]:
    if ss.aperto:
        schermata_dettaglio(*ss.aperto)
    else:
        schermata_elenco()
elif pagina == PAGINE[2]:
    schermata_piano()
elif pagina == PAGINE[3]:
    schermata_impara()
else:
    schermata_test()
