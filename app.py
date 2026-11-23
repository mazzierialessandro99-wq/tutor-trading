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

import logica as L

st.set_page_config(page_title="Tutor di Trading", page_icon="📈", layout="centered")

# ==============================================================================
# STILE
# ==============================================================================
# Colori: serie dei grafici e colori di stato (verde/giallo/rosso riservati al semaforo)
C_SU, C_GIU = "#199e70", "#e66767"   # candele in salita / in discesa
C_EMA, C_RSI, C_ATR = "#3987e5", "#9085e9", "#c98500"
STATO = {"VERDE": "#0ca30c", "GIALLO": "#fab219", "ROSSO": "#d03b3b"}

st.markdown(
    """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 4rem; max-width: 780px;}
h1, h2, h3 {letter-spacing: -0.01em;}

.hero {border-radius: 20px; padding: 22px 22px 18px; margin-bottom: 8px;
       background: radial-gradient(120% 140% at 0% 0%, #1f3550 0%, #18221f 55%, #141716 100%);
       border: 1px solid #2a3330;}
.hero h1 {margin: 0; padding: 0; font-size: 1.9rem;}
.hero p {margin: 6px 0 0; color: #c3c2b7; font-size: 0.95rem;}
.pill {display: inline-block; font-size: 0.72rem; font-weight: 600; letter-spacing: .04em;
       padding: 3px 10px; border-radius: 999px; background: #233; color: #9fd3c0;
       border: 1px solid #2f4a44; margin-bottom: 10px;}

.card {background: #1c1f1e; border: 1px solid #2c302e; border-radius: 16px;
       padding: 14px 16px; margin: 10px 0;}
.card b {color: #f0efec;}

/* Semaforo */
.sem {display: flex; gap: 18px; align-items: center; border-radius: 20px; padding: 18px;
      margin: 6px 0 12px; border: 1px solid; }
.luci {display: flex; flex-direction: column; gap: 8px; background: #0d0f0e;
       padding: 10px 9px; border-radius: 16px; border: 1px solid #2c302e;}
.luce {width: 26px; height: 26px; border-radius: 50%; background: #2a2d2c; opacity: .55;}
.luce.on {opacity: 1;}
.sem-colore {font-size: 1.7rem; font-weight: 800; letter-spacing: .02em; line-height: 1.1;}
.sem-txt {color: #e6e5e0; margin-top: 4px; font-size: 1rem;}
.sem-meta {color: #a9a89f; font-size: 0.8rem; margin-top: 8px;}

/* Spie (perché) */
.spia {display: flex; gap: 12px; align-items: flex-start;}
.spia .ico {font-size: 1.3rem; line-height: 1.4;}
.spia .tit {font-weight: 700; margin-bottom: 2px;}
.spia .txt, .card .txt {color: #d5d4cd; font-size: 0.93rem; line-height: 1.45;}

/* Passi operativi */
.passo {display: flex; gap: 14px; align-items: flex-start; background: #1c1f1e;
        border: 1px solid #2c302e; border-radius: 16px; padding: 14px 16px; margin: 10px 0;}
.num {flex: 0 0 34px; height: 34px; border-radius: 50%; background: #0ca30c22;
      border: 1px solid #0ca30c; color: #7be07b; font-weight: 800; display: flex;
      align-items: center; justify-content: center;}
.passo .tit {font-weight: 700; margin-bottom: 4px;}
.passo .val {font-size: 1.45rem; font-weight: 800; color: #f0efec; margin: 2px 0;}
.passo .txt {color: #d5d4cd; font-size: 0.92rem; line-height: 1.45;}
.campi {display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin-top: 8px; font-size: 0.92rem;}
.campi span:nth-child(odd) {color: #a9a89f;}
.campi span:nth-child(even) {font-weight: 700; color: #f0efec;}

/* Riquadri dei valori: 4 in fila sul PC, 2x2 sul telefono */
.tiles {display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 4px 0 8px;}
@media (max-width: 640px) {.tiles {grid-template-columns: repeat(2, 1fr);}}
.tile {background: #1c1f1e; border: 1px solid #2c302e; border-radius: 14px; padding: 10px 12px;}
.tile .k {color: #a9a89f; font-size: 0.78rem;}
.tile .v {font-size: 1.3rem; font-weight: 800; color: #f0efec; margin: 2px 0;}
.tile .s {color: #a9a89f; font-size: 0.78rem;}

[data-testid="stMetricValue"] {font-size: 1.5rem;}
[data-testid="stExpander"] details {border-radius: 14px;}
</style>
""",
    unsafe_allow_html=True,
)


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


# ==============================================================================
# INTESTAZIONE E SCHEDE
# ==============================================================================
st.markdown(
    """
<div class="hero">
  <div class="pill">SOLO ANALISI · NESSUN ORDINE AUTOMATICO</div>
  <h1>📈 Tutor di Trading</h1>
  <p>Il tuo assistente per imparare e analizzare. Decidi e operi sempre tu, a mano, sul conto <b>demo</b>.</p>
</div>
""",
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(["🎓 Regole", "🚦 Segnali", "🧪 Backtest"])


# ==============================================================================
# TAB 1 — PERCHÉ E REGOLE D'ORO
# ==============================================================================
with tab1:
    st.subheader("Perché e regole d'oro")
    st.caption("Leggi questa scheda **prima** di guardare i segnali. Sono le regole che ti tengono in gioco.")

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
        df_rec = pd.DataFrame({
            "Se perdi": [f"−{p}%" for p in perdite],
            "Per tornare in pari ti serve": [f"+{p / (100 - p) * 100:.0f}%" for p in perdite],
        })
        st.dataframe(df_rec, hide_index=True, width="stretch")
        st.info("Perdere il 50% significa dover poi **raddoppiare** il capitale solo per tornare al punto di partenza.")

    with st.expander("2️⃣  Gli indicatori che usiamo: EMA 200, RSI, ATR"):
        st.markdown(
            f"""
Un indicatore è un **calcolo fatto sui prezzi passati** che ci aiuta a leggere il grafico.
Non predice il futuro: ci dà un quadro ordinato della situazione.

| Indicatore | A cosa serve | Come lo leggiamo |
|---|---|---|
| **EMA 200** | **Trend** (la direzione di fondo) | Prezzo **sopra** la linea → trend positivo. **Sotto** → trend negativo: non compriamo |
| **RSI (14)** | **Timing** (il momento) | Va da 0 a 100. Tra **{L.RSI_MIN} e {L.RSI_MAX}** il prezzo ha fatto una pausa: possibile occasione *se il trend è positivo*. Sopra **{L.RSI_TIRATO}** è “tirato”: meglio non inseguirlo |
| **ATR (14)** | **Volatilità** (quanto si muove) | È l'escursione media di una giornata. Ci dice **quanto largo mettere lo stop** per non farci buttare fuori dal rumore |
"""
        )
        st.markdown("**Esempio illustrativo** (prezzi inventati): il prezzo sta sopra la sua EMA 200, quindi il trend è positivo.")
        rng = np.random.default_rng(7)
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0008, 0.012, 400))))
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=s, name="Prezzo", line=dict(width=1.5, color="#c3c2b7")))
        fig.add_trace(go.Scatter(y=s.ewm(span=200, adjust=False).mean(), name="EMA 200",
                                 line=dict(width=2.5, color=C_EMA)))
        fig.update_layout(height=260, margin=dict(l=8, r=8, t=8, b=8), template="plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=1.12), xaxis_title="giorni", hovermode="x unified")
        fig.update_xaxes(gridcolor="#262a28")
        fig.update_yaxes(gridcolor="#262a28")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with st.expander("3️⃣  Stop Loss, Take Profit e la regola dell'1%"):
        st.markdown(
            """
- **Stop Loss (SL)**: il prezzo a cui l'operazione si **chiude da sola in perdita**.
  Lo decidi *prima* di entrare, a mente fredda. È la tua cintura di sicurezza.
- **Take Profit (TP)**: il prezzo a cui l'operazione si **chiude da sola in guadagno**.
- **Rapporto Rischio/Rendimento 1:2**: il TP è lontano dall'entrata **il doppio** dello SL.
  Così anche vincendo solo **4 operazioni su 10** il conto può restare in attivo.

**La regola dell'1%:** su una singola operazione non rischi mai più dell'**1% del capitale**.
Con 1.000 € significa al massimo **10 €** di perdita se tocca lo stop.
Anche 10 perdite di fila (capita!) ti lasciano circa il 90% del capitale.

La quantità da comprare **non si sceglie a sentimento**, si calcola:
"""
        )
        st.latex(r"\text{quote} = \frac{\text{capitale} \times 1\%}{\text{prezzo di entrata} - \text{stop loss}}")

        st.markdown("**Prova tu** — calcolatrice della posizione:")
        c1, c2 = st.columns(2)
        cap = c1.number_input("Capitale (€)", min_value=100.0, value=1000.0, step=100.0, key="t1_cap")
        rischio_t1 = c2.number_input("Rischio (%)", min_value=0.1, max_value=2.0, value=1.0, step=0.1, key="t1_risk")
        c3, c4 = st.columns(2)
        entrata = c3.number_input("Prezzo di entrata", min_value=0.01, value=50.0, step=0.5, key="t1_in")
        stop = c4.number_input("Stop Loss", min_value=0.01, value=48.0, step=0.5, key="t1_sl")

        if stop >= entrata:
            st.error("Per un acquisto lo Stop Loss deve stare **sotto** il prezzo di entrata.")
        else:
            rischio_eur = cap * rischio_t1 / 100
            dist = entrata - stop
            quote = rischio_eur / dist
            if quote * entrata > cap:
                quote = cap / entrata
            tp = entrata + 2 * dist
            m1, m2, m3 = st.columns(3)
            m1.metric("Rischio massimo", f"{fmt_num(rischio_eur)} €")
            m2.metric("Quote", fmt_quote(quote))
            m3.metric("Capitale impegnato", f"{fmt_num(quote * entrata, 0)} €")
            st.success(
                f"Compri **{fmt_quote(quote)} quote** a **{fmt_prezzo(entrata)}**, Stop Loss a **{fmt_prezzo(stop)}**, "
                f"Take Profit a **{fmt_prezzo(tp)}** (1:2). Se va male perdi circa **{fmt_num(quote * dist)} €**, "
                f"se va bene guadagni circa **{fmt_num(quote * dist * 2)} €**."
            )
            st.caption("Le quote frazionarie (es. 4,37) si possono comprare solo su alcuni broker: altrimenti arrotonda **per difetto**.")

    with st.expander("4️⃣  Le regole d'oro in una schermata"):
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
        st.warning("Questa dashboard ha scopo **didattico** e non costituisce consulenza finanziaria.")


# ==============================================================================
# TAB 2 — ANALISI E SEGNALI OPERATIVI
# ==============================================================================
def grafico(df: pd.DataFrame, nome: str) -> go.Figure:
    verdi = df[df["Semaforo"] == "VERDE"]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        row_heights=[0.62, 0.2, 0.18],
                        subplot_titles=(nome, "RSI (14) · timing", "ATR (14) · volatilità"))
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                 name="Prezzo", increasing=dict(line=dict(color=C_SU, width=1), fillcolor=C_SU),
                                 decreasing=dict(line=dict(color=C_GIU, width=1), fillcolor=C_GIU)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA200"], name="EMA 200", line=dict(color=C_EMA, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=verdi.index, y=verdi["Low"] - verdi["ATR"] * 0.6, mode="markers",
                             name="Semaforo verde", marker=dict(symbol="triangle-up", size=11, color=STATO["VERDE"],
                                                                line=dict(width=1.5, color="#121413")),
                             hovertemplate="Semaforo verde<extra></extra>"), row=1, col=1)

    # Fascia del ritracciamento e linea del "tirato" nel pannello RSI
    fig.add_shape(type="rect", xref="x2 domain", yref="y2", x0=0, x1=1, y0=L.RSI_MIN, y1=L.RSI_MAX,
                  fillcolor=STATO["VERDE"], opacity=0.18, line_width=0, layer="below")
    fig.add_shape(type="line", xref="x2 domain", yref="y2", x0=0, x1=1, y0=L.RSI_TIRATO, y1=L.RSI_TIRATO,
                  line=dict(color="#9a998f", width=1.2, dash="dot"))
    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI", line=dict(color=C_RSI, width=2),
                             showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["ATR"], name="ATR", line=dict(color=C_ATR, width=2),
                             showlegend=False), row=3, col=1)

    fine = df.index[-1]
    inizio = fine - pd.Timedelta(days=365)
    vis = df[df.index >= inizio]
    pad = (vis["High"].max() - vis["Low"].min()) * 0.05
    fig.update_xaxes(range=[inizio, fine + pd.Timedelta(days=5)], rangeslider_visible=False, tickformat="%m/%Y", hoverformat="%d/%m/%Y",
                     gridcolor="#232725", showspikes=True, spikemode="across", spikecolor="#6b6a63", spikethickness=1)
    fig.update_yaxes(gridcolor="#232725", zeroline=False)
    fig.update_yaxes(range=[vis["Low"].min() - pad, vis["High"].max() + pad], row=1, col=1)
    fig.update_yaxes(range=[0, 100], tickvals=[L.RSI_MIN, L.RSI_MAX, L.RSI_TIRATO], row=2, col=1)
    fig.update_yaxes(range=[0, vis["ATR"].max() * 1.15], row=3, col=1)
    fig.update_layout(height=640, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=6, r=6, t=30, b=6),
                      hovermode="x unified", dragmode="pan", font=dict(color="#c3c2b7"), separators=",.",
                      legend=dict(orientation="h", y=-0.04, x=0, font=dict(size=12)))
    fig.update_annotations(font=dict(size=13, color="#c3c2b7"), x=0, xanchor="left")
    return fig


def riquadro_semaforo(v: dict):
    col = v["colore"]
    luci = "".join(
        f'<span class="luce{" on" if c == col else ""}" style="background:{STATO[c] if c == col else "#2a2d2c"};'
        f'{"box-shadow:0 0 18px " + STATO[c] + ";" if c == col else ""}"></span>'
        for c in ("ROSSO", "GIALLO", "VERDE")
    )
    st.markdown(
        f"""
<div class="sem" style="border-color:{STATO[col]}66; background:linear-gradient(135deg,{STATO[col]}1f,#1c1f1e 70%);">
  <div class="luci">{luci}</div>
  <div>
    <div class="sem-colore" style="color:{STATO[col]}">{col}</div>
    <div class="sem-txt">{v["sintesi"]}</div>
    <div class="sem-meta">Ultima chiusura: {v["data"]:%d/%m/%Y} · dati Yahoo Finance, in ritardo</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def spie(v: dict):
    icone = {"ok": "✅", "forse": "⚠️", "no": "⛔", "info": "📏"}
    for stato, titolo, testo in v["spie"]:
        st.markdown(
            f'<div class="card spia"><div class="ico">{icone[stato]}</div>'
            f'<div><div class="tit">{titolo}</div><div class="txt">{html_testo(testo)}</div></div></div>',
            unsafe_allow_html=True,
        )


def passo(n: int, titolo: str, valore: str, testo: str):
    st.markdown(
        f'<div class="passo"><div class="num">{n}</div><div style="flex:1">'
        f'<div class="tit">{titolo}</div><div class="val">{valore}</div>'
        f'<div class="txt">{html_testo(testo)}</div></div></div>',
        unsafe_allow_html=True,
    )


def passi_operativi(p: dict, v: dict, nome: str, valuta: str, cambio: float, rischio_pct: float):
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta + " ")
    eur = lambda x: fmt_num(x / cambio)   # importo nella valuta dell'asset -> euro
    nota_cambio = "" if valuta == "EUR" else f" (prezzi in {valuta}, cambio 1 € = {fmt_num(cambio, 4)} {valuta})"

    passo(1, "Quante quote comprare", f"{fmt_quote(p['quote'])} quote",
          f"Impegni circa **{eur(p['impegno'])} €** del tuo capitale. Sono calcolate perché, se tocca lo stop, "
          f"perdi al massimo circa **{eur(p['perdita'])} €**, cioè il {fmt_num(rischio_pct, 2).rstrip('0').rstrip(',')}% "
          f"del capitale{nota_cambio}."
          + (" ⚠️ Il numero è stato **ridotto** per non impegnare più del tuo capitale: il rischio reale è più basso."
             if p["limitato"] else ""))
    passo(2, "Prezzo di ingresso", f"{sim}{fmt_prezzo(p['ingresso'])}",
          "È l'ultima chiusura. I dati sono in ritardo: **controlla il prezzo vero sul broker**. "
          f"Se è già salito oltre **{sim}{fmt_prezzo(p['ingresso'] + 0.5 * v['atr'])}** (mezzo ATR), "
          "non inseguirlo: salta l'occasione.")
    passo(3, "Stop Loss", f"{sim}{fmt_prezzo(p['stop'])}",
          f"È {fmt_num(L.STOP_ATR, 0)} volte l'ATR sotto l'ingresso ({sim}{fmt_num(p['distanza'], 4 if p['ingresso'] < 10 else 2)}). "
          "Così le normali oscillazioni di una o due giornate non ti fanno uscire per sbaglio; "
          "se invece il prezzo scende davvero fin lì, l'idea era sbagliata e si esce con una perdita piccola.")
    passo(4, "Take Profit", f"{sim}{fmt_prezzo(p['tp'])}",
          f"È a **{fmt_num(L.RR, 0)} volte** la distanza dello stop (rapporto 1:{fmt_num(L.RR, 0)}). "
          f"Se ci arriva guadagni circa **{eur(p['guadagno'])} €**: il doppio di quello che rischi.")
    st.markdown(
        f"""
<div class="passo"><div class="num">5</div><div style="flex:1">
  <div class="tit">Cosa compilare sul broker</div>
  <div class="txt">Controlla che in alto ci sia scritto <b>DEMO</b>, cerca <b>{nome}</b> e apri il modulo d'ordine:</div>
  <div class="campi">
    <span>Direzione</span><span>Compra / Buy</span>
    <span>Tipo d'ordine</span><span>Limite / Limit</span>
    <span>Prezzo limite</span><span>{fmt_prezzo(p['ingresso'])}</span>
    <span>Quantità</span><span>{fmt_quote(p['quote'])}</span>
    <span>Stop Loss</span><span>{fmt_prezzo(p['stop'])}</span>
    <span>Take Profit</span><span>{fmt_prezzo(p['tp'])}</span>
  </div>
  <div class="txt" style="margin-top:8px">Rileggi i numeri e conferma. Poi scrivi nel diario data, asset e motivo.
  Se il broker usa i <b>lotti</b> (CFD), controlla prima quanto vale un lotto per questo strumento.</div>
</div></div>
""",
        unsafe_allow_html=True,
    )


with tab2:
    st.subheader("Analisi e segnali")

    nomi = list(L.ASSET) + ["✏️ Altro (scrivi il simbolo)"]
    c1, c2 = st.columns([3, 2])
    scelta = c1.selectbox("Asset da analizzare", nomi, key="asset")
    capitale = c2.number_input("Il tuo capitale (€)", min_value=100.0, value=1000.0, step=100.0, key="capitale")
    if scelta.startswith("✏️"):
        ticker = st.text_input("Simbolo Yahoo Finance", value="ENI.MI",
                               help="Lo trovi su finance.yahoo.com: es. ENI.MI, ISP.MI, TSLA, AMZN, ETH-USD").strip().upper()
        nome, valuta = ticker, None
    else:
        ticker, valuta = L.ASSET[scelta]
        nome = scelta
    rischio_pct = st.select_slider("Rischio per operazione", options=[0.25, 0.5, 0.75, 1.0], value=1.0,
                                   format_func=lambda x: f"{fmt_num(x, 2).rstrip('0').rstrip(',')}% del capitale",
                                   help="La regola d'oro è non superare l'1%. Chi inizia può scendere allo 0,5%.")

    with st.spinner("Scarico i prezzi…"):
        try:
            dati = scarica(ticker)
        except Exception:
            dati = pd.DataFrame()

    if len(dati) < L.EMA_PERIODO + 50:
        st.error(f"Non riesco a scaricare abbastanza dati per **{ticker}**. Controlla il simbolo o riprova tra qualche minuto "
                 "(Yahoo ogni tanto limita le richieste).")
    else:
        df = prepara(dati)
        v = L.valuta(df)

        riquadro_semaforo(v)

        var = (v["close"] / df["Close"].iloc[-2] - 1) * 100
        tiles = [("Prezzo", fmt_prezzo(v["close"]),
                  f'<span style="color:{C_SU if var >= 0 else C_GIU}">{"▲" if var >= 0 else "▼"} {fmt_num(abs(var))}%</span>'),
                 ("EMA 200", fmt_prezzo(v["ema"]), "trend"),
                 ("RSI", f"{v['rsi']:.0f}", "timing"),
                 ("ATR", fmt_prezzo(v["atr"]), "volatilità")]
        st.markdown(
            '<div class="tiles">' + "".join(
                f'<div class="tile"><div class="k">{k}</div><div class="v">{val}</div><div class="s">{s}</div></div>'
                for k, val, s in tiles) + "</div>",
            unsafe_allow_html=True,
        )

        st.plotly_chart(grafico(df, nome), width="stretch",
                        config={"displayModeBar": False, "scrollZoom": False})
        st.caption("Ultimi 12 mesi: trascina il grafico per andare indietro nel tempo. I triangoli verdi segnano i giorni "
                   f"in cui il semaforo era verde; la fascia verde nell'RSI è la zona del ritracciamento ({L.RSI_MIN}-{L.RSI_MAX}).")

        st.markdown("#### Perché il semaforo è " + v["colore"].lower())
        spie(v)

        valuta = valuta or valuta_ticker(ticker)
        cambio = cambio_eur(valuta)
        if cambio is None:
            st.warning(f"Non riesco a leggere il cambio euro/{valuta}: i calcoli sono fatti come se 1 € = 1 {valuta}.")
            cambio = 1.0
        p = L.piano(capitale * cambio, rischio_pct, v["close"], v["atr"])

        if v["colore"] == "VERDE":
            st.markdown("#### ✅ Cosa fare, passo per passo")
            passi_operativi(p, v, nome, valuta, cambio, rischio_pct)
        else:
            cosa = ("Niente: **non si compra**. Controlla un altro asset qui sotto oppure torna domani."
                    if v["colore"] == "ROSSO" else
                    "**Aspetta.** Il semaforo diventa verde quando il trend è chiaramente positivo e l'RSI, "
                    f"dopo essere sceso tra {L.RSI_MIN} e {L.RSI_MAX}, ricomincia a salire. Ricontrolla domani a mercato chiuso.")
            st.markdown("#### 🕰️ Cosa fare adesso")
            st.markdown(f'<div class="card"><div class="txt">{html_testo(cosa)}</div></div>', unsafe_allow_html=True)
            with st.expander("📘 Esercizio: come sarebbero i numeri se oggi fosse verde"):
                st.caption("Solo per imparare a leggere il riquadro. **Oggi non è un'operazione da fare.**")
                passi_operativi(p, v, nome, valuta, cambio, rischio_pct)

    st.markdown("#### 🔎 Controlla tutti gli asset")
    if st.button("Mostra il semaforo di tutti gli asset", width="stretch"):
        righe = []
        etichette = {"VERDE": "🟢 Verde", "GIALLO": "🟡 Giallo", "ROSSO": "🔴 Rosso"}
        with st.spinner("Controllo gli asset…"):
            for n, (t, _) in L.ASSET.items():
                try:
                    d = scarica(t)
                    if len(d) < L.EMA_PERIODO + 50:
                        continue
                    vv = L.valuta(L.aggiungi_indicatori(d))
                    righe.append({"Semaforo": etichette[vv["colore"]], "Asset": n, "RSI": round(vv["rsi"]),
                                  "Distanza da EMA 200": f"{(vv['close'] / vv['ema'] - 1) * 100:+.1f}%"})
                except Exception:
                    continue
        if righe:
            ordine = {e: i for i, e in enumerate(etichette.values())}
            righe.sort(key=lambda r: ordine[r["Semaforo"]])
            st.dataframe(pd.DataFrame(righe), hide_index=True, width="stretch")
        else:
            st.error("Non sono riuscito a scaricare i dati. Riprova tra qualche minuto.")

    st.caption("Scopo didattico: non è consulenza finanziaria. Gli ordini li inserisci tu, sul conto demo.")


# ==============================================================================
# TAB 3 — in costruzione
# ==============================================================================
with tab3:
    st.subheader("Verifica sul passato")
    st.info("🚧 In costruzione: è il prossimo passo. Qui proveremo queste stesse regole sugli ultimi 3 anni.")
