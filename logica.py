"""
LOGICA DEL TUTOR — indicatori, semaforo e calcolo dell'operazione.
Qui non c'è grafica: solo i calcoli, così si possono leggere e verificare da soli.
Gli stessi calcoli li usa anche il backtest (Tab 3).
"""
from __future__ import annotations

import pandas as pd

# ------------------------------------------------------------------------------
# REGOLE (modificabili): sono le stesse spiegate a schermo
# ------------------------------------------------------------------------------
EMA_PERIODO = 200
RSI_PERIODO = 14
ATR_PERIODO = 14
RSI_MIN = 30           # sotto: crollo troppo forte, non è un semplice ritracciamento
RSI_MAX = 45           # sopra: il prezzo non ha ritracciato abbastanza
RSI_TIRATO = 70        # sopra: ipercomprato
DIST_MIN_EMA_ATR = 1.0 # prezzo a meno di 1 ATR dalla EMA 200 = trend incerto
STOP_ATR = 2.0         # Stop Loss = ingresso - 2 x ATR
RR = 2.0               # Take Profit = 2 volte la distanza dello stop

# Asset proposti: nome -> (ticker yfinance, valuta dei prezzi)
ASSET = {
    "S&P 500 (indice USA)": ("^GSPC", "USD"),
    "Nasdaq 100 (tecnologia USA)": ("^NDX", "USD"),
    "Oro": ("GC=F", "USD"),
    "Bitcoin": ("BTC-USD", "USD"),
    "Apple": ("AAPL", "USD"),
    "Microsoft": ("MSFT", "USD"),
    "Nvidia": ("NVDA", "USD"),
    "Euro / Dollaro": ("EURUSD=X", "USD"),
}


# ------------------------------------------------------------------------------
# INDICATORI
# ------------------------------------------------------------------------------
def aggiungi_indicatori(df: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge EMA 200, RSI 14 e ATR 14 (metodo di Wilder) a un DataFrame con Open/High/Low/Close."""
    df = df.copy()
    df["EMA200"] = df["Close"].ewm(span=EMA_PERIODO, adjust=False).mean()

    delta = df["Close"].diff()
    guadagni = delta.clip(lower=0).ewm(alpha=1 / RSI_PERIODO, adjust=False).mean()
    perdite = (-delta.clip(upper=0)).ewm(alpha=1 / RSI_PERIODO, adjust=False).mean()
    rs = guadagni / perdite.replace(0, float("nan"))
    df["RSI"] = (100 - 100 / (1 + rs)).fillna(100)

    chiusura_prec = df["Close"].shift(1)
    true_range = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - chiusura_prec).abs(),
        (df["Low"] - chiusura_prec).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = true_range.ewm(alpha=1 / ATR_PERIODO, adjust=False).mean()
    return df


def it(x: float, dec: int = 1) -> str:
    """Numero all'italiana (1.234,5)."""
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------------------
# SEMAFORO
# ------------------------------------------------------------------------------
def semaforo_riga(close: float, ema: float, rsi: float, rsi_ieri: float, atr: float) -> str:
    """Restituisce 'VERDE', 'GIALLO' o 'ROSSO' per una singola giornata."""
    if close < ema:
        return "ROSSO"
    if close - ema < DIST_MIN_EMA_ATR * atr:
        return "GIALLO"
    if RSI_MIN <= rsi <= RSI_MAX and rsi > rsi_ieri:
        return "VERDE"
    return "GIALLO"


def valuta(df: pd.DataFrame) -> dict:
    """Legge l'ultima giornata e spiega il semaforo in italiano semplice."""
    ult, prec = df.iloc[-1], df.iloc[-2]
    close, ema, rsi, rsi_ieri, atr = ult["Close"], ult["EMA200"], ult["RSI"], prec["RSI"], ult["ATR"]
    colore = semaforo_riga(close, ema, rsi, rsi_ieri, atr)
    dist_atr = (close - ema) / atr
    dist_pct = (close / ema - 1) * 100

    # Le tre "spie": trend, timing, volatilità. Ognuna: (stato, titolo, spiegazione)
    if close < ema:
        trend = ("no", "Trend negativo",
                 f"Il prezzo è **sotto** la EMA 200 (−{it(abs(dist_pct))}%). Da mesi scende più di quanto salga: "
                 "comprare adesso significherebbe andare contro corrente.")
    elif dist_atr < DIST_MIN_EMA_ATR:
        trend = ("forse", "Trend incerto",
                 f"Il prezzo è sopra la EMA 200 ma vicinissimo ({it(dist_atr)} ATR): è sul confine tra salita e discesa. "
                 "Meglio aspettare che la direzione sia chiara.")
    else:
        trend = ("ok", "Trend positivo",
                 f"Il prezzo è **sopra** la EMA 200 (+{it(dist_pct)}%, cioè {it(dist_atr)} ATR): la direzione di fondo è al rialzo.")

    if rsi > RSI_TIRATO:
        timing = ("no", "Prezzo tirato",
                  f"RSI a **{rsi:.0f}**: è salito molto e in fretta (sopra {RSI_TIRATO}). Comprare qui è come salire su un treno già partito.")
    elif rsi > RSI_MAX:
        timing = ("forse", "Nessun ritracciamento",
                  f"RSI a **{rsi:.0f}**: il prezzo non ha ancora fatto una pausa. Aspettiamo che l'RSI scenda tra {RSI_MIN} e {RSI_MAX}.")
    elif rsi < RSI_MIN:
        timing = ("forse", "Discesa troppo forte",
                  f"RSI a **{rsi:.0f}**: sotto {RSI_MIN} non è più una pausa ma una caduta. Aspettiamo che si stabilizzi.")
    elif rsi <= rsi_ieri:
        timing = ("forse", "Ritracciamento in corso",
                  f"RSI a **{rsi:.0f}**, nella zona giusta, ma **sta ancora scendendo** (ieri {rsi_ieri:.0f}). "
                  "Aspettiamo il primo giorno in cui risale: è il segno che la discesa si sta fermando.")
    else:
        timing = ("ok", "Momento giusto",
                  f"RSI a **{rsi:.0f}** e **in risalita** (ieri {rsi_ieri:.0f}): il prezzo ha fatto una pausa e sta ripartendo.")

    atr_pct = atr / close * 100
    volat = ("info", "Volatilità",
             f"ATR = **{it(atr, 4 if close < 10 else 2)}** ({it(atr_pct)}% del prezzo): in media si muove così in una giornata. "
             f"Per questo lo Stop Loss va a {STOP_ATR:g} ATR di distanza.")

    sintesi = {
        "VERDE": "Opportunità di acquisto: trend positivo e ritracciamento che sta finendo.",
        "GIALLO": "Attendere: il trend non è negativo, ma il momento non è quello giusto.",
        "ROSSO": "Non operare: il trend è negativo.",
    }[colore]

    return {"colore": colore, "sintesi": sintesi, "spie": [trend, timing, volat],
            "close": close, "ema": ema, "rsi": rsi, "atr": atr, "data": df.index[-1]}


# ------------------------------------------------------------------------------
# CALCOLO DELL'OPERAZIONE
# ------------------------------------------------------------------------------
def piano(capitale: float, rischio_pct: float, ingresso: float, atr: float) -> dict:
    """Quote, Stop Loss e Take Profit per rischiare al massimo rischio_pct del capitale."""
    distanza = STOP_ATR * atr
    stop = ingresso - distanza
    tp = ingresso + RR * distanza
    rischio = capitale * rischio_pct / 100
    quote = rischio / distanza
    limitato = False
    if quote * ingresso > capitale:     # non si può impegnare più di quanto si ha (niente leva)
        quote = capitale / ingresso
        limitato = True
    return {"ingresso": ingresso, "stop": stop, "tp": tp, "quote": quote,
            "impegno": quote * ingresso, "perdita": quote * distanza,
            "guadagno": quote * distanza * RR, "rischio_max": rischio,
            "distanza": distanza, "limitato": limitato}
