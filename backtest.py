"""
BACKTEST — come sarebbero andate le regole del semaforo negli ultimi anni, seguendo il tuo piano.

Regole simulate (le stesse della sentinella):
  • segnale: il semaforo di un mercato DIVENTA verde alla chiusura di un giorno
  • ingresso: all'apertura del giorno dopo (come farebbe la sentinella)
  • stop-loss: ingresso − 2 ATR · take profit: ingresso + 4 ATR (rapporto 1:2)
  • se in un giorno vengono toccati sia stop sia take profit, si conta lo STOP (ipotesi prudente)
  • se dopo 60 giorni non è successo niente, si chiude alla chiusura
  • rischio per operazione del piano (1%, 0,5% sulle cripto) calcolato sul capitale iniziale
  • al massimo 3 operazioni aperte insieme, una sola per mercato
  • costi (spread e commissioni) stimati allo 0,1% del prezzo per ogni operazione

Uso:  python backtest.py            (scarica 5 anni da Yahoo e simula gli ultimi 3)
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import logica as L

ANNI = 3
MAX_GIORNI = 60
COSTO_PCT = 0.001


def segnali_mercato(df: pd.DataFrame) -> pd.DataFrame:
    """Indicatori e semaforo di ogni giorno."""
    df = L.aggiungi_indicatori(df)
    rsi_ieri = df["RSI"].shift(1)
    df["Semaforo"] = [L.semaforo_riga(c, e, r, rp, a) for c, e, r, rp, a in
                      zip(df["Close"], df["EMA200"], df["RSI"], rsi_ieri, df["ATR"])]
    df["Nuovo_verde"] = (df["Semaforo"] == "VERDE") & (df["Semaforo"].shift(1) != "VERDE")
    return df


def simula_operazione(df: pd.DataFrame, i: int) -> dict | None:
    """Operazione nata dal segnale del giorno i (ingresso all'apertura del giorno i+1)."""
    if i + 1 >= len(df):
        return None
    atr = df["ATR"].iloc[i]
    ingresso = df["Open"].iloc[i + 1]
    distanza = L.STOP_ATR * atr
    stop, tp = ingresso - distanza, ingresso + L.RR * distanza
    fine = min(len(df) - 1, i + MAX_GIORNI)
    for j in range(i + 1, fine + 1):
        o, h, l = df["Open"].iloc[j], df["High"].iloc[j], df["Low"].iloc[j]
        if j > i + 1 and o <= stop:          # apertura già sotto lo stop: si esce all'apertura (peggio dello stop)
            return {"j": j, "uscita": o, "esito": "stop"}
        if l <= stop:
            return {"j": j, "uscita": stop, "esito": "stop"}
        if h >= tp:
            return {"j": j, "uscita": tp, "esito": "take profit"}
    if fine == len(df) - 1 and fine - i < MAX_GIORNI:
        return {"j": fine, "uscita": df["Close"].iloc[fine], "esito": "ancora aperta"}
    return {"j": fine, "uscita": df["Close"].iloc[fine], "esito": "tempo scaduto"}


def esegui(dati: dict[str, pd.DataFrame], capitale: float, piano: dict, anni: int = ANNI) -> dict:
    """Simula il portafoglio sui mercati forniti. dati: ticker -> DataFrame giornaliero."""
    nomi = {t: n for n, (t, _) in L.ASSET.items()}
    candidati = []
    inizio = None
    for t, grezzo in dati.items():
        if len(grezzo) < L.EMA_PERIODO + 60:
            continue
        df = segnali_mercato(grezzo)
        limite = df.index[-1] - pd.DateOffset(years=anni)
        inizio = limite if inizio is None else min(inizio, limite)
        for i in np.flatnonzero(df["Nuovo_verde"].to_numpy()):
            if df.index[i] < limite or i < L.EMA_PERIODO:
                continue
            esito = simula_operazione(df, i)
            if not esito:
                continue
            ingresso = df["Open"].iloc[i + 1]
            distanza = L.STOP_ATR * df["ATR"].iloc[i]
            r_lordo = (esito["uscita"] - ingresso) / distanza
            r_netto = r_lordo - COSTO_PCT * ingresso / distanza
            candidati.append({"ticker": t, "mercato": nomi.get(t, t), "entrata": df.index[i + 1],
                              "uscita": df.index[esito["j"]], "esito": esito["esito"], "R": r_netto,
                              "rischio_pct": L.rischio_per(t, piano)})

    # Portafoglio: in ordine di data, max N aperte, una per mercato
    candidati.sort(key=lambda c: c["entrata"])
    max_aperte = int(piano.get("max_posizioni_aperte", 3))
    aperte, operazioni = [], []
    for c in candidati:
        aperte = [a for a in aperte if a["uscita"] > c["entrata"]]
        if len(aperte) >= max_aperte or any(a["ticker"] == c["ticker"] for a in aperte):
            continue
        c["euro"] = c["R"] * capitale * c["rischio_pct"] / 100
        aperte.append(c)
        operazioni.append(c)

    return riassunto(operazioni, capitale, inizio)


def riassunto(operazioni: list[dict], capitale: float, inizio) -> dict:
    chiuse = [o for o in operazioni if o["esito"] != "ancora aperta"]
    if not chiuse:
        return {"operazioni": [], "n": 0}
    df = pd.DataFrame(chiuse).sort_values("uscita")
    curva = capitale + df.groupby("uscita")["euro"].sum().cumsum()
    curva = pd.concat([pd.Series([capitale], index=[pd.Timestamp(inizio)]), curva])
    picco = curva.cummax()
    dd = (curva - picco) / picco * 100
    vinte, perse = df[df["euro"] > 0], df[df["euro"] <= 0]
    lordo_v, lordo_p = vinte["euro"].sum(), -perse["euro"].sum()
    finale = float(curva.iloc[-1])
    anni = max((curva.index[-1] - curva.index[0]).days / 365.25, 0.1)
    per_mercato = (df.groupby("mercato").agg(operazioni=("euro", "size"), euro=("euro", "sum"),
                                             vinte=("euro", lambda s: (s > 0).mean() * 100))
                   .sort_values("euro", ascending=False).reset_index())
    # serie di perdite consecutive più lunga
    serie, peggiore = 0, 0
    for e in df["euro"]:
        serie = serie + 1 if e <= 0 else 0
        peggiore = max(peggiore, serie)
    return {
        "n": len(df),
        "win_rate": len(vinte) / len(df) * 100,
        "media_vinta": float(vinte["euro"].mean()) if len(vinte) else 0.0,
        "media_persa": float(perse["euro"].mean()) if len(perse) else 0.0,
        "profit_factor": lordo_v / lordo_p if lordo_p else float("inf"),
        "R_medio": float(df["R"].mean()),
        "finale": finale,
        "rendimento_pct": (finale / capitale - 1) * 100,
        "annuo_pct": ((finale / capitale) ** (1 / anni) - 1) * 100 if finale > 0 else -100.0,
        "max_dd_pct": float(dd.min()),
        "perdite_di_fila": peggiore,
        "durata_media": float((df["uscita"] - df["entrata"]).dt.days.mean()),
        "curva": curva,
        "drawdown": dd,
        "per_mercato": per_mercato,
        "operazioni": df,
        "aperte_ora": len(operazioni) - len(chiuse),
    }


def verdetto(r: dict) -> tuple[str, str]:
    """('buono'|'debole'|'negativo', spiegazione)"""
    if r.get("n", 0) < 20:
        return "debole", "Troppe poche operazioni per giudicare: servono più dati prima di fidarsi."
    pf, dd = r["profit_factor"], r["max_dd_pct"]
    if pf >= 1.3 and dd > -15:
        return "buono", "Le regole hanno guadagnato con perdite sotto controllo. Vale la pena metterle alla prova sul Demo."
    if pf >= 1.05:
        return "debole", ("Hanno guadagnato poco rispetto al rischio: il margine è sottile e basta un periodo sfortunato "
                          "per andare in perdita. Da migliorare prima di fidarsi.")
    return "negativo", "Le regole avrebbero perso soldi. Non vanno usate così: vanno corrette."


def main():
    import sentinella as S
    tickers = [t for t, _ in L.ASSET.values()]
    dati = S.scarica_tutti(tickers, periodo="5y")
    if not dati:
        sys.exit("Nessun dato da Yahoo.")
    piano = L.carica_piano()
    r = esegui(dati, float(piano.get("capitale", 1000)), piano)
    if not r["n"]:
        print("Nessuna operazione nel periodo.")
        return
    giudizio, spiegazione = verdetto(r)
    print(f"Mercati con dati: {len(dati)} · periodo: {r['curva'].index[0]:%d/%m/%Y} → {r['curva'].index[-1]:%d/%m/%Y}")
    print(f"Operazioni chiuse: {r['n']} (ancora aperte: {r['aperte_ora']})")
    print(f"Win rate: {r['win_rate']:.1f}% · media vinta {r['media_vinta']:.2f} € · media persa {r['media_persa']:.2f} €")
    print(f"Profit factor: {r['profit_factor']:.2f} · R medio: {r['R_medio']:.3f}")
    print(f"Capitale: 1000 → {r['finale']:.2f} € ({r['rendimento_pct']:+.1f}%, {r['annuo_pct']:+.1f}% annuo)")
    print(f"Drawdown massimo: {r['max_dd_pct']:.1f}% · perdite di fila: {r['perdite_di_fila']} · durata media {r['durata_media']:.0f} giorni")
    print(f"VERDETTO: {giudizio.upper()} — {spiegazione}")
    print("\nPer mercato:")
    print(r["per_mercato"].to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    esiti = r["operazioni"]["esito"].value_counts().to_dict()
    print("\nEsiti:", json.dumps(esiti, ensure_ascii=False))


if __name__ == "__main__":
    main()
