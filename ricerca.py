"""
RICERCA — il bot studia quali regole funzionano e QUANDO operare, senza ingannarsi.

Confronta, con costi e commissioni notturne inclusi:
  STRATEGIE   ritracciamento (attuale: EMA 200 + RSI) · rottura dei massimi a 55 giorni (con TP 1:2 e 1:3)
  GESTIONE    stop fisso · stop spostato a pareggio quando l'operazione guadagna quanto rischia
  QUANDO      sempre · solo con il mercato USA in trend positivo (S&P 500 sopra la sua EMA 200)
              · e volatilità non estrema · solo quando le ultime 20 occasioni studiate hanno reso (fiducia)

REGOLA FISSATA PRIMA DI GUARDARE I RISULTATI (per non scegliere il "fortunato"):
  una configurazione è promossa solo se ha profit factor >= 1,2 sui 20 mercati
  E profit factor >= 1,2 con risultato positivo sui 54 mercati MAI usati per costruire le regole.
  Tra le promosse vince quella con il profit factor più alto sui mercati mai visti.
Ogni decisione del filtro usa SOLO dati passati rispetto al giorno dell'operazione.

Uso:  python ricerca.py      (su GitHub: Actions -> Ricerca -> Run workflow)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import backtest as B
import logica as L

ROTTURA_GIORNI = 55
FIDUCIA_N = 20
SOGLIA_PF = 1.2


# ------------------------------------------------------------------------------
# SEGNALI
# ------------------------------------------------------------------------------
def segnali(df: pd.DataFrame, strategia: str) -> np.ndarray:
    """Indici dei giorni con un NUOVO segnale di acquisto (si entra all'apertura del giorno dopo)."""
    if strategia == "ritracciamento":
        return np.flatnonzero(df["Nuovo_verde"].to_numpy())
    if strategia == "rottura":
        massimo = df["High"].shift(1).rolling(ROTTURA_GIORNI).max()
        sopra = (df["Close"] > massimo) & (df["Close"] > df["EMA200"])
        nuovo = sopra & ~sopra.shift(1, fill_value=False)
        return np.flatnonzero(nuovo.to_numpy())
    raise ValueError(strategia)


def simula(df: pd.DataFrame, i: int, rr: float, pareggio: bool, ticker: str) -> dict | None:
    if i + 1 >= len(df):
        return None
    ingresso = df["Open"].iloc[i + 1]
    distanza = L.STOP_ATR * df["ATR"].iloc[i]
    stop, tp = ingresso - distanza, ingresso + rr * distanza
    fine = min(len(df) - 1, i + B.MAX_GIORNI)
    uscita, esito, j_fine = None, None, fine
    for j in range(i + 1, fine + 1):
        o, h, l = df["Open"].iloc[j], df["High"].iloc[j], df["Low"].iloc[j]
        if j > i + 1 and o <= stop:
            uscita, esito, j_fine = o, "stop", j
            break
        if l <= stop:
            uscita, esito, j_fine = stop, "stop", j
            break
        if h >= tp:
            uscita, esito, j_fine = tp, "take profit", j
            break
        if pareggio and h >= ingresso + distanza:       # da domani lo stop sta al prezzo d'ingresso
            stop = max(stop, ingresso)
    if uscita is None:
        if fine == len(df) - 1 and fine - i < B.MAX_GIORNI:
            return None                                  # ancora aperta: non si conta
        uscita, esito = df["Close"].iloc[fine], "tempo scaduto"
    giorni = max(1, (df.index[j_fine] - df.index[i + 1]).days)
    r = (uscita - ingresso) / distanza - B.COSTO_PCT * ingresso / distanza \
        - ingresso * B.swap_annuo(ticker) / 365 * giorni / distanza
    return {"entrata": df.index[i + 1], "uscita": df.index[j_fine], "esito": esito, "R": r}


# ------------------------------------------------------------------------------
# QUANDO OPERARE (regime di mercato) — solo dati passati
# ------------------------------------------------------------------------------
def regime(spx: pd.DataFrame) -> pd.DataFrame:
    d = L.aggiungi_indicatori(spx)
    atr_pct = d["ATR"] / d["Close"]
    soglia = atr_pct.rolling(252, min_periods=120).quantile(0.8)
    out = pd.DataFrame(index=d.index)
    out["trend"] = d["Close"] > d["EMA200"]
    out["calmo"] = atr_pct <= soglia
    return out


def permesso(reg: pd.DataFrame, giorno, filtro: str) -> bool:
    if filtro in ("sempre", "fiducia"):
        return True
    prima = reg.loc[:giorno - pd.Timedelta(days=1)]     # decisione presa con i dati fino al giorno prima
    if prima.empty:
        return False
    r = prima.iloc[-1]
    if filtro == "trend":
        return bool(r["trend"])
    if filtro in ("trend+calmo", "trend+fiducia"):
        return bool(r["trend"]) and (filtro == "trend+fiducia" or bool(r["calmo"]))
    raise ValueError(filtro)


# ------------------------------------------------------------------------------
# PORTAFOGLIO
# ------------------------------------------------------------------------------
def prova(indicatori: dict, reg: pd.DataFrame, piano: dict, strategia: str, rr: float, pareggio: bool,
          filtro: str, capitale: float) -> dict:
    nomi = {t: n for n, (t, _) in (L.ASSET | L.ASSET_EXTRA).items()}
    candidati, inizio = [], None
    for t, df in indicatori.items():
        limite = df.index[-1] - pd.DateOffset(years=B.ANNI)
        inizio = limite if inizio is None else min(inizio, limite)
        for i in segnali(df, strategia):
            if i < L.EMA_PERIODO or df.index[i] < limite:
                continue
            o = simula(df, i, rr, pareggio, t)
            if o:
                o.update({"ticker": t, "mercato": nomi.get(t, t), "rischio_pct": L.rischio_per(t, piano)})
                candidati.append(o)
    candidati.sort(key=lambda c: c["entrata"])
    studiati = sorted(candidati, key=lambda c: c["uscita"])     # tutte le occasioni, prese o no: il "quaderno" del bot
    max_aperte = int(piano.get("max_posizioni_aperte", 3))
    aperte, operazioni = [], []
    for c in candidati:
        if not permesso(reg, c["entrata"], filtro):
            continue
        if "fiducia" in filtro:
            passate = [s["R"] for s in studiati if s["uscita"] < c["entrata"]][-FIDUCIA_N:]
            if len(passate) < FIDUCIA_N or np.mean(passate) <= 0:
                continue
        aperte = [a for a in aperte if a["uscita"] > c["entrata"]]
        if len(aperte) >= max_aperte or any(a["ticker"] == c["ticker"] for a in aperte):
            continue
        c = dict(c, euro=c["R"] * capitale * c["rischio_pct"] / 100)
        aperte.append(c)
        operazioni.append(c)
    return B.riassunto(operazioni, capitale, inizio)


CONFIGURAZIONI = [(s, rr, be, f)
                  for s, rr in (("ritracciamento", 2.0), ("rottura", 2.0), ("rottura", 3.0))
                  for be in (False, True)
                  for f in ("sempre", "trend", "trend+calmo", "fiducia", "trend+fiducia")]


def main():
    import sentinella as S
    piano = L.carica_piano()
    capitale = float(piano.get("capitale", 500))
    base = [t for t, _ in L.ASSET.values()]
    extra = [t for t, _ in L.ASSET_EXTRA.values()]
    dati = S.scarica_tutti(base + extra + ["^GSPC"], periodo="5y")
    reg = regime(dati["^GSPC"])
    ind = {}
    for t, d in dati.items():
        if len(d) >= L.EMA_PERIODO + 60:
            df = B.segnali_mercato(d)
            ind[t] = df
    ind_base = {t: ind[t] for t in base if t in ind}
    ind_extra = {t: ind[t] for t in extra if t in ind}
    print(f"Mercati: {len(ind_base)} base + {len(ind_extra)} mai visti · costi e commissioni notturne inclusi\n")
    print(f"{'Strategia':<15}{'TP':>4} {'Pareggio':<9}{'Quando':<15}| {'Op':>4}{'Vinte':>7}{'PF':>6}{'Ris.':>8}{'DD':>7} "
          f"| {'Op':>4}{'Vinte':>7}{'PF':>6}{'Ris.':>8}{'DD':>7} | Esito")
    righe = []
    for s, rr, be, f in CONFIGURAZIONI:
        a = prova(ind_base, reg, piano, s, rr, be, f, capitale)
        b = prova(ind_extra, reg, piano, s, rr, be, f, capitale)
        if not a.get("n") or not b.get("n"):
            continue
        promossa = a["profit_factor"] >= SOGLIA_PF and b["profit_factor"] >= SOGLIA_PF and b["rendimento_pct"] > 0
        righe.append((s, rr, be, f, a, b, promossa))
        print(f"{s:<15}{rr:>4.0f} {('sì' if be else 'no'):<9}{f:<15}| {a['n']:>4}{a['win_rate']:>6.0f}%{a['profit_factor']:>6.2f}"
              f"{a['rendimento_pct']:>7.1f}%{a['max_dd_pct']:>6.1f}% | {b['n']:>4}{b['win_rate']:>6.0f}%{b['profit_factor']:>6.2f}"
              f"{b['rendimento_pct']:>7.1f}%{b['max_dd_pct']:>6.1f}% | {'✅ PROMOSSA' if promossa else '—'}")
    promosse = [r for r in righe if r[6]]
    print()
    if promosse:
        s, rr, be, f, a, b, _ = max(promosse, key=lambda r: r[5]["profit_factor"])
        print(f"VINCITRICE: {s} · TP 1:{rr:.0f} · pareggio {'sì' if be else 'no'} · quando: {f}")
        print(f"   20 mercati: PF {a['profit_factor']:.2f}, {a['rendimento_pct']:+.1f}% · "
              f"mai visti: PF {b['profit_factor']:.2f}, {b['rendimento_pct']:+.1f}%")
    else:
        print("NESSUNA configurazione supera la regola: nessuna ha un vantaggio affidabile anche sui mercati mai visti.")


if __name__ == "__main__":
    main()
