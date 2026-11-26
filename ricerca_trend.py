"""
RICERCA "TREND SUI MESI" (time-series momentum) — la famiglia di strategie con le prove più solide sul lungo periodo.

Come funziona (una volta al mese, l'ultimo giorno di borsa):
  • per ogni mercato si guarda il rendimento degli ultimi N mesi (N = 3, 6 o 12; "12-1" = 12 mesi saltando l'ultimo)
  • se è positivo si COMPRA; se è negativo si sta fuori (solo acquisti) oppure si VENDE allo scoperto (acquisti e vendite)
  • quanto mettere su ogni mercato: meno sui mercati agitati, di più su quelli calmi (volatilità obiettivo 40% l'anno
    per mercato, divisa per il numero di mercati) — leva totale massima 3
  • i pesi restano fermi fino al mese dopo
Costi: spread a ogni cambio di peso (stima per tipo di mercato) + commissioni notturne dei CFD su tutta la posizione.
Periodo: gli ultimi 10 anni. Mercati: i 20 base + gli 63 mai usati per costruire le regole.

REGOLA FISSATA PRIMA DI GUARDARE I RISULTATI:
  promossa solo se, dopo i costi, ha Sharpe >= 0,5 E rendimento annuo positivo SIA sui 20 mercati SIA sui mai visti.
  (Sharpe = rendimento diviso per l'oscillazione: 0,5 è "decente", 1 è "ottimo")
L'esito va in ricerca_trend.json: NON cambia cosa fa il bot finché non decidiamo insieme.

Uso:  python ricerca_trend.py      (su GitHub: Actions -> Ricerca trend -> Run workflow)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import backtest as B
import logica as L

ANNI = 10
VOL_OBIETTIVO = 0.40
LEVA_MAX = 3.0
SOGLIA_SHARPE = 0.5
COSTI = {"indici": 0.0002, "valute": 0.0001, "materie": 0.0004, "azioni": 0.001, "cripto": 0.002}
CONFIGURAZIONI = [(n, lato) for n in ("3", "6", "12", "12-1") for lato in ("solo acquisti", "acquisti e vendite")]


def costo(t: str) -> float:
    if L.is_cripto(t):
        return COSTI["cripto"]
    if t.endswith("=X"):
        return COSTI["valute"]
    if t.endswith("=F"):
        return COSTI["materie"]
    if t.startswith("^") or t == "FTSEMIB.MI":
        return COSTI["indici"]
    return COSTI["azioni"]


def simula(chiusure: pd.DataFrame, lookback: str, lato: str) -> pd.Series:
    """Rendimenti giornalieri del portafoglio, costi inclusi. chiusure: colonne = ticker, righe = giorni."""
    ret = chiusure.pct_change(fill_method=None)
    vol = ret.rolling(63, min_periods=40).std() * np.sqrt(252)
    fine_mese = chiusure.groupby(chiusure.index.to_period("M")).tail(1).index
    if lookback == "12-1":
        mom = chiusure.shift(21) / chiusure.shift(252) - 1
    else:
        mom = chiusure / chiusure.shift(21 * int(lookback)) - 1
    pesi = pd.DataFrame(np.nan, index=chiusure.index, columns=chiusure.columns)
    for g in fine_mese:
        m, v = mom.loc[g], vol.loc[g]
        validi = m.notna() & v.notna() & (v > 0)
        if not validi.any():
            continue
        segno = np.sign(m[validi])
        if lato == "solo acquisti":
            segno = segno.clip(lower=0)
        w = segno * (VOL_OBIETTIVO / v[validi]) / validi.sum()
        if w.abs().sum() > LEVA_MAX:
            w *= LEVA_MAX / w.abs().sum()
        pesi.loc[g] = w.reindex(chiusure.columns).fillna(0)
    pesi = pesi.ffill().fillna(0)
    tenuti = pesi.shift(1).fillna(0)                       # si entra alla chiusura del giorno del segnale
    lordo = (tenuti * ret.fillna(0)).sum(axis=1)
    cambi = pesi.diff().abs().fillna(pesi.abs())
    c_spread = (cambi * pd.Series({t: costo(t) for t in chiusure.columns})).sum(axis=1).shift(1).fillna(0)
    swap = pd.Series({t: B.swap_annuo(t) for t in chiusure.columns})
    c_notte = (tenuti.abs() * swap).sum(axis=1) / 252
    return lordo - c_spread - c_notte


def misura(r: pd.Series) -> dict:
    r = r[r.index >= r.index[-1] - pd.DateOffset(years=ANNI)]
    curva = (1 + r).cumprod()
    anni = max((r.index[-1] - r.index[0]).days / 365.25, 0.1)
    annuo = curva.iloc[-1] ** (1 / anni) - 1
    vol = r.std() * np.sqrt(252)
    discesa = (curva / curva.cummax() - 1).min()
    mensili = (1 + r).groupby(r.index.to_period("Y")).prod() - 1
    return {"annuo_pct": round(float(annuo * 100), 2), "volatilita_pct": round(float(vol * 100), 2),
            "sharpe": round(float(annuo / vol) if vol > 0 else 0.0, 3), "max_dd_pct": round(float(discesa * 100), 2),
            "anni_positivi": f"{int((mensili > 0).sum())} su {len(mensili)}",
            "per_anno": {str(k): round(float(v * 100), 1) for k, v in mensili.items()}}


def chiusure_di(dati: dict, tickers: list[str]) -> pd.DataFrame:
    serie = {t: dati[t]["Close"] for t in tickers if t in dati}
    df = pd.DataFrame(serie).sort_index()
    return df.ffill(limit=5)                                # festività diverse tra mercati


def main():
    import sentinella as S
    base = [t for t, _ in L.ASSET.values()]
    extra = [t for t, _ in L.ASSET_EXTRA.values()]
    dati = S.scarica_tutti(base + extra + ["^GSPC"], periodo="max")
    gruppi = {"20 mercati": chiusure_di(dati, base), "mai visti": chiusure_di(dati, extra)}
    print(f"Mercati: {gruppi['20 mercati'].shape[1]} base + {gruppi['mai visti'].shape[1]} mai visti · ultimi {ANNI} anni · costi inclusi\n")
    riferimento = misura(dati["^GSPC"]["Close"].pct_change().dropna())
    print(f"Riferimento: comprare e tenere l'S&P 500 → {riferimento['annuo_pct']:+.1f}% l'anno, Sharpe {riferimento['sharpe']:.2f}, "
          f"discesa peggiore {riferimento['max_dd_pct']:.1f}%\n")
    print(f"{'Mesi':<6}{'Lato':<20}| {'Annuo':>7}{'Sharpe':>7}{'Discesa':>9} | {'Annuo':>7}{'Sharpe':>7}{'Discesa':>9} | Esito")
    righe = []
    for n, lato in CONFIGURAZIONI:
        a = misura(simula(gruppi["20 mercati"], n, lato))
        b = misura(simula(gruppi["mai visti"], n, lato))
        promossa = a["sharpe"] >= SOGLIA_SHARPE and b["sharpe"] >= SOGLIA_SHARPE and a["annuo_pct"] > 0 and b["annuo_pct"] > 0
        righe.append({"mesi": n, "lato": lato, "base": a, "mai_visti": b, "promossa": bool(promossa)})
        print(f"{n:<6}{lato:<20}| {a['annuo_pct']:>6.1f}%{a['sharpe']:>7.2f}{a['max_dd_pct']:>8.1f}% | "
              f"{b['annuo_pct']:>6.1f}%{b['sharpe']:>7.2f}{b['max_dd_pct']:>8.1f}% | {'✅ PROMOSSA' if promossa else '—'}")
    # diagnosi: quanto pesano le commissioni notturne dei CFD? (stesse regole, come se si comprassero ETF/azioni vere)
    B.CON_SWAP = False
    senza = {}
    for n, lato in CONFIGURAZIONI:
        if lato == "solo acquisti":
            a = misura(simula(gruppi["20 mercati"], n, lato))
            b = misura(simula(gruppi["mai visti"], n, lato))
            senza[n] = {"base": a, "mai_visti": b}
            print(f"senza commissioni notturne · {n:<5} mesi | {a['annuo_pct']:>6.1f}%{a['sharpe']:>7.2f}{a['max_dd_pct']:>8.1f}% | "
                  f"{b['annuo_pct']:>6.1f}%{b['sharpe']:>7.2f}{b['max_dd_pct']:>8.1f}%")
    B.CON_SWAP = True
    promosse = [r for r in righe if r["promossa"]]
    vincitrice = max(promosse, key=lambda r: r["mai_visti"]["sharpe"]) if promosse else None
    print()
    if vincitrice:
        print(f"VINCITRICE: {vincitrice['mesi']} mesi, {vincitrice['lato']}")
        print("Anno per anno (mai visti):", vincitrice["mai_visti"]["per_anno"])
    else:
        print("NESSUNA configurazione supera la regola.")
    esito = {"data": pd.Timestamp.now(tz="Europe/Rome").isoformat(timespec="minutes"),
             "regola": f"Sharpe >= {SOGLIA_SHARPE} e rendimento annuo positivo sui 20 mercati e sui mai visti, costi inclusi",
             "riferimento_sp500": riferimento, "configurazioni": righe, "senza_commissioni_notturne": senza, "vincitrice": vincitrice}
    with open("ricerca_trend.json", "w", encoding="utf-8") as f:
        json.dump(esito, f, indent=1, ensure_ascii=False)
    print("Esito salvato in ricerca_trend.json")


if __name__ == "__main__":
    main()
