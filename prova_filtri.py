"""
PROVA DEI FILTRI SU EVENTI E TENSIONE — servono davvero? Lo misuriamo sul passato prima di fidarci.

Strategia di base del bot (ritracciamento, TP 1:2), ultimi 3 anni, costi inclusi, 20 mercati + 54 mai visti, in 4 versioni:
  nessuno · eventi (niente operazioni prima dei conti trimestrali e delle decisioni della Fed)
  · tensione (rischio dimezzato con VIX > 30 il giorno prima) · tutti e due
Si guarda soprattutto se i filtri RIDUCONO LE DISCESE senza peggiorare troppo il risultato: sono freni, non motori.
Uso:  python prova_filtri.py      (su GitHub: Actions -> Prova filtri -> Run workflow)
"""
from __future__ import annotations

import json

import pandas as pd

import backtest as B
import eventi as E
import logica as L
import ricerca as R


def storico_conti(ticker: str) -> list:
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=24)
        return sorted({d.date() for d in df.index})
    except Exception as e:
        print(f"  conti di {ticker} non disponibili ({str(e)[:60]})")
        return []


def main():
    import sentinella as S
    piano = L.carica_piano()
    capitale = float(piano.get("capitale", 1000))
    base = [t for t, _ in L.ASSET.values()]
    extra = [t for t, _ in L.ASSET_EXTRA.values()]
    dati = S.scarica_tutti(base + extra + ["^GSPC", "^VIX"], periodo="5y")
    reg = R.regime(dati["^GSPC"])
    vix = dati["^VIX"]["Close"]
    conti = {t: storico_conti(t) for t in base + extra if E.is_azione(t)}
    print(f"Date dei conti trovate per {sum(bool(v) for v in conti.values())} azioni su {len(conti)}\n")
    ind = {t: B.segnali_mercato(d) for t, d in dati.items() if len(d) >= L.EMA_PERIODO + 60 and t != "^VIX"}
    gruppi = {"20 mercati": {t: ind[t] for t in base if t in ind}, "mai visti": {t: ind[t] for t in extra if t in ind}}
    originale = R.simula

    def con_filtri(modo: str):
        def simula(df, i, rr, pareggio, t):
            o = originale(df, i, rr, pareggio, t)
            if not o:
                return o
            g = o["entrata"].date()
            if modo in ("eventi", "tutti"):
                if t in E.SENSIBILI_FED and any(0 <= (f - g).days <= 1 for f in E.FED_STORICHE):
                    return None
                if any(0 <= (c - g).days <= E.GIORNI_PRIMA_CONTI for c in conti.get(t, [])):
                    return None
            if modo in ("tensione", "tutti"):
                prima = vix.loc[:pd.Timestamp(g) - pd.Timedelta(days=1)]
                if len(prima) and prima.iloc[-1] > E.VIX_SOGLIA:
                    o = dict(o, R=o["R"] * 0.5)
            return o
        return simula

    esito = {"data": pd.Timestamp.now(tz="Europe/Rome").isoformat(timespec="minutes"), "risultati": []}
    print(f"{'Filtri':<10}{'Gruppo':<12}| {'Op':>4}{'Vinte':>7}{'PF':>6}{'Ris.':>8}{'Discesa':>9}")
    for modo in ("nessuno", "eventi", "tensione", "tutti"):
        R.simula = con_filtri(modo)
        for nome, ind_g in gruppi.items():
            r = R.prova(ind_g, reg, piano, "ritracciamento", 2.0, False, "sempre", capitale)
            if not r.get("n"):
                continue
            print(f"{modo:<10}{nome:<12}| {r['n']:>4}{r['win_rate']:>6.0f}%{r['profit_factor']:>6.2f}"
                  f"{r['rendimento_pct']:>7.1f}%{r['max_dd_pct']:>8.1f}%")
            esito["risultati"].append({"filtri": modo, "gruppo": nome, "operazioni": int(r["n"]),
                                       "win_rate": round(float(r["win_rate"]), 1), "profit_factor": round(float(r["profit_factor"]), 3),
                                       "rendimento_pct": round(float(r["rendimento_pct"]), 2), "max_dd_pct": round(float(r["max_dd_pct"]), 2)})
    R.simula = originale
    with open("prova_filtri.json", "w", encoding="utf-8") as f:
        json.dump(esito, f, indent=1, ensure_ascii=False)
    print("\nEsito salvato in prova_filtri.json")


if __name__ == "__main__":
    main()
