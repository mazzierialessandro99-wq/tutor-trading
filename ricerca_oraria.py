"""
RICERCA SULLE CANDELE ORARIE — le stesse regole della ricerca settimanale, ma ora per ora.

Serve a rispondere a una domanda: operare più spesso (ogni ora invece che ogni giorno) dà un vantaggio?
  • dati: candele da 1 ora degli ultimi ~2 anni (il massimo gratuito di Yahoo), 20 mercati + 54 mai visti
  • strategie: ritracciamento (EMA 200 + RSI, su ore) e rottura dei massimi delle ultime 55 ore, TP 1:2 e 1:3
  • gestione: stop fisso o spostato a pareggio · quando: sempre / S&P 500 in trend / trend e volatilità non estrema
  • costi per operazione stimati sugli spread di Capital.com per tipo di mercato (più bassi dello 0,1% del
    giornaliero: così l'orario NON è penalizzato) + commissioni notturne solo per le notti passate davvero
  • stessa regola d'esame fissata prima: PF >= 1,2 sui 20 mercati E PF >= 1,2 con risultato positivo sui mai visti
L'esito va in ricerca_oraria.json: NON cambia cosa fa il bot finché non decidiamo insieme.

Uso:  python ricerca_oraria.py      (su GitHub: Actions -> Ricerca oraria -> Run workflow)
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import backtest as B
import logica as L
import ricerca as R
import sentinella as S

MAX_BARRE = 80                 # se dopo 80 ore di mercato non è successo niente, si chiude
COSTI = {"indici": 0.0002, "valute": 0.0001, "materie": 0.0004, "azioni": 0.001, "cripto": 0.002}


def costo(ticker: str) -> float:
    if L.is_cripto(ticker):
        return COSTI["cripto"]
    if ticker.endswith("=X"):
        return COSTI["valute"]
    if ticker.endswith("=F"):
        return COSTI["materie"]
    if ticker.startswith("^") or ticker == "FTSEMIB.MI":
        return COSTI["indici"]
    return COSTI["azioni"]


_cache: dict = {}


def simula(df, i: int, rr: float, pareggio: bool, ticker: str) -> dict | None:
    k = id(df)
    if k not in _cache:
        _cache[k] = (df["Open"].to_numpy(), df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy(),
                     df["ATR"].to_numpy(), df.index)
    O, H, Lo, C, A, idx = _cache[k]
    if i + 1 >= len(O):
        return None
    ingresso, distanza = O[i + 1], L.STOP_ATR * A[i]
    if not distanza > 0:
        return None
    stop, tp = ingresso - distanza, ingresso + rr * distanza
    fine = min(len(O) - 1, i + MAX_BARRE)
    uscita, esito, j = None, None, fine
    for j in range(i + 1, fine + 1):
        if j > i + 1 and O[j] <= stop:
            uscita, esito = O[j], "stop"
            break
        if Lo[j] <= stop:
            uscita, esito = stop, "stop"
            break
        if H[j] >= tp:
            uscita, esito = tp, "take profit"
            break
        if pareggio and H[j] >= ingresso + distanza:
            stop = max(stop, ingresso)
    if uscita is None:
        if fine == len(O) - 1 and fine - i < MAX_BARRE:
            return None
        uscita, esito, j = C[fine], "tempo scaduto", fine
    notti = (idx[j].normalize() - idx[i + 1].normalize()).days
    r = (uscita - ingresso) / distanza - costo(ticker) * ingresso / distanza \
        - ingresso * B.swap_annuo(ticker) / 365 * notti / distanza
    return {"entrata": idx[i + 1], "uscita": idx[j], "esito": esito, "R": r}


def main():
    originale = S.scarica_tutti
    S.scarica_tutti = lambda tickers, periodo="730d": originale(tickers, periodo="730d", intervallo="1h")
    R.simula = simula
    R.CONFIGURAZIONI = [c for c in R.CONFIGURAZIONI if "fiducia" not in c[3]]   # il filtro "fiducia" è troppo lento su ore
    B.ANNI = 2
    qui = Path.cwd()
    lavoro = tempfile.mkdtemp()
    os.chdir(lavoro)                 # così NON sovrascrive ricerca_esito.json, che guida il bot
    try:
        print("RICERCA SU CANDELE DA 1 ORA (circa 2 anni)\n")
        R.main()
        shutil.move(os.path.join(lavoro, "ricerca_esito.json"), qui / "ricerca_oraria.json")
        print("Esito salvato in ricerca_oraria.json")
    finally:
        os.chdir(qui)


if __name__ == "__main__":
    main()
