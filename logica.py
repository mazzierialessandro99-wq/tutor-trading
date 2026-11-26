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

# Mercati sorvegliati: nome -> (ticker yfinance, valuta dei prezzi)
# Sono tra i più scambiati e si trovano tutti anche su Capital.com. Si possono aggiungere o togliere.
ASSET = {
    # Indici
    "S&P 500 (USA)": ("^GSPC", "USD"),
    "Nasdaq 100 (USA)": ("^NDX", "USD"),
    "Dow Jones (USA)": ("^DJI", "USD"),
    "DAX (Germania)": ("^GDAXI", "EUR"),
    "FTSE MIB (Italia)": ("FTSEMIB.MI", "EUR"),
    "Euro Stoxx 50": ("^STOXX50E", "EUR"),
    # Materie prime
    "Oro": ("GC=F", "USD"),
    "Argento": ("SI=F", "USD"),
    "Petrolio WTI": ("CL=F", "USD"),
    # Valute
    "Euro / Dollaro": ("EURUSD=X", "USD"),
    "Sterlina / Dollaro": ("GBPUSD=X", "USD"),
    # Criptovalute
    "Bitcoin": ("BTC-USD", "USD"),
    "Ethereum": ("ETH-USD", "USD"),
    # Azioni
    "Apple": ("AAPL", "USD"),
    "Microsoft": ("MSFT", "USD"),
    "Nvidia": ("NVDA", "USD"),
    "Amazon": ("AMZN", "USD"),
    "Alphabet (Google)": ("GOOGL", "USD"),
    "Meta": ("META", "USD"),
    "Tesla": ("TSLA", "USD"),
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


# ------------------------------------------------------------------------------
# IL MIO PIANO (piano.json): rischio, limiti e orari personali
# ------------------------------------------------------------------------------
def carica_piano() -> dict:
    import json
    from pathlib import Path
    f = Path(__file__).with_name("piano.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def is_cripto(ticker: str) -> bool:
    return ticker.endswith("-USD") and "=" not in ticker


def rischio_per(ticker: str, piano: dict, rischio_base: float | None = None) -> float:
    """% di capitale da rischiare su questo mercato: le cripto, più nervose, hanno un rischio ridotto."""
    base = rischio_base if rischio_base is not None else piano.get("rischio_per_operazione", 1.0)
    if is_cripto(ticker):
        return min(base, piano.get("rischio_cripto", base))
    return base


# ------------------------------------------------------------------------------
# NOMI SU CAPITAL.COM (cosa scrivere nella ricerca dell'app). Da confermare con l'API.
# ------------------------------------------------------------------------------
NOMI_CAPITAL = {
    "^GSPC": "US500", "^NDX": "US100", "^DJI": "US30", "^GDAXI": "DE40", "FTSEMIB.MI": "IT40",
    "^STOXX50E": "EU50", "GC=F": "Gold", "SI=F": "Silver", "CL=F": "US Crude Oil",
    "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana", "XRP-USD": "XRP", "BNB-USD": "BNB", "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin", "LTC-USD": "Litecoin", "AVAX-USD": "Avalanche", "DOT-USD": "Polkadot", "LINK-USD": "Chainlink",
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "META": "Meta Platforms", "TSLA": "Tesla",
}


def nome_capital(ticker: str, nome: str) -> str:
    return NOMI_CAPITAL.get(ticker, nome)


# ------------------------------------------------------------------------------
# MERCATI AGGIUNTIVI (universo esteso). Scelti a priori con un criterio fisso:
# i più grandi e scambiati, disponibili su Capital.com, quotati in dollari o euro.
# NON scelti guardando i risultati del backtest (sarebbe barare).
# ------------------------------------------------------------------------------
ASSET_EXTRA = {
    # Cripto (oltre a Bitcoin ed Ethereum)
    "Solana": ("SOL-USD", "USD"), "XRP": ("XRP-USD", "USD"), "BNB": ("BNB-USD", "USD"), "Cardano": ("ADA-USD", "USD"), "Dogecoin": ("DOGE-USD", "USD"), "Litecoin": ("LTC-USD", "USD"), "Avalanche": ("AVAX-USD", "USD"), "Polkadot": ("DOT-USD", "USD"), "Chainlink": ("LINK-USD", "USD"),
    # Indici
    "Russell 2000 (USA)": ("^RUT", "USD"), "CAC 40 (Francia)": ("^FCHI", "EUR"),
    "AEX (Olanda)": ("^AEX", "EUR"), "IBEX 35 (Spagna)": ("^IBEX", "EUR"),
    # Materie prime e valute
    "Gas naturale": ("NG=F", "USD"), "Rame": ("HG=F", "USD"), "Platino": ("PL=F", "USD"),
    "Dollaro australiano / Dollaro": ("AUDUSD=X", "USD"), "Dollaro neozelandese / Dollaro": ("NZDUSD=X", "USD"),
    # Grandi aziende USA
    "Broadcom": ("AVGO", "USD"), "JPMorgan": ("JPM", "USD"), "Visa": ("V", "USD"), "Mastercard": ("MA", "USD"),
    "UnitedHealth": ("UNH", "USD"), "ExxonMobil": ("XOM", "USD"), "Johnson & Johnson": ("JNJ", "USD"),
    "Procter & Gamble": ("PG", "USD"), "Home Depot": ("HD", "USD"), "Costco": ("COST", "USD"),
    "Eli Lilly": ("LLY", "USD"), "AbbVie": ("ABBV", "USD"), "Coca-Cola": ("KO", "USD"), "PepsiCo": ("PEP", "USD"),
    "Walmart": ("WMT", "USD"), "Bank of America": ("BAC", "USD"), "Oracle": ("ORCL", "USD"),
    "Salesforce": ("CRM", "USD"), "AMD": ("AMD", "USD"), "Netflix": ("NFLX", "USD"), "Adobe": ("ADBE", "USD"),
    "Intel": ("INTC", "USD"), "Cisco": ("CSCO", "USD"), "Disney": ("DIS", "USD"), "McDonald's": ("MCD", "USD"),
    "Nike": ("NKE", "USD"), "Boeing": ("BA", "USD"), "Caterpillar": ("CAT", "USD"), "Goldman Sachs": ("GS", "USD"),
    "IBM": ("IBM", "USD"), "Qualcomm": ("QCOM", "USD"), "Pfizer": ("PFE", "USD"), "Merck": ("MRK", "USD"),
    "Chevron": ("CVX", "USD"),
    # Grandi aziende europee
    "SAP": ("SAP.DE", "EUR"), "ASML": ("ASML.AS", "EUR"), "LVMH": ("MC.PA", "EUR"), "Siemens": ("SIE.DE", "EUR"),
    "TotalEnergies": ("TTE.PA", "EUR"), "Allianz": ("ALV.DE", "EUR"), "ENI": ("ENI.MI", "EUR"),
    "Enel": ("ENEL.MI", "EUR"), "Intesa Sanpaolo": ("ISP.MI", "EUR"), "UniCredit": ("UCG.MI", "EUR"),
    "Ferrari": ("RACE.MI", "EUR"),
}


def mercati(piano: dict | None = None) -> dict:
    """Mercati sorvegliati secondo il piano: 'base' (20) oppure 'esteso' (base + aggiuntivi)."""
    piano = piano if piano is not None else {}
    return ASSET | ASSET_EXTRA if piano.get("universo") == "esteso" else dict(ASSET)


def piano_distanza(capitale: float, rischio_pct: float, ingresso: float, distanza: float) -> dict:
    """Come piano(), ma con una distanza dello stop scelta (es. sotto il minimo recente)."""
    stop = ingresso - distanza
    tp = ingresso + RR * distanza
    rischio = capitale * rischio_pct / 100
    quote = rischio / distanza
    limitato = False
    if quote * ingresso > capitale:
        quote = capitale / ingresso
        limitato = True
    return {"ingresso": ingresso, "stop": stop, "tp": tp, "quote": quote,
            "impegno": quote * ingresso, "perdita": quote * distanza,
            "guadagno": quote * distanza * RR, "rischio_max": rischio,
            "distanza": distanza, "limitato": limitato}
