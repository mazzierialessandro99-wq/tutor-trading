"""
COACH — il tutor sul singolo mercato.

Legge la situazione (trend, momento, volatilità, supporti e resistenze) e prepara:
  • cosa FARE e cosa NON fare, in parole semplici
  • dove mettere lo stop loss: 3 metodi a confronto, con prezzo, quantità e quello consigliato
  • dove sta il take profit rispetto ai massimi recenti
Nessun calcolo nascosto: ogni consiglio dice il perché.
"""
from __future__ import annotations

import pandas as pd

import logica as L

STOP_PCT = 0.03          # stop "a percentuale" (per confronto: è il metodo che sconsigliamo)
MARGINE_ATR = 0.25       # margine sotto il minimo recente, per non stare esattamente dove stanno tutti
GIORNI_SUPPORTO = 10
GIORNI_RESISTENZA = 60


def _it(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analizza(df: pd.DataFrame) -> dict:
    """df: prezzi giornalieri con EMA200, RSI, ATR (come in logica.aggiungi_indicatori)."""
    u, ieri = df.iloc[-1], df.iloc[-2]
    close, ema, rsi, atr = float(u["Close"]), float(u["EMA200"]), float(u["RSI"]), float(u["ATR"])
    dist_atr = (close - ema) / atr
    pendenza = (ema / float(df["EMA200"].iloc[-21]) - 1) * 100 if len(df) > 21 else 0.0
    atr_pct = df["ATR"] / df["Close"]
    finestra = atr_pct.iloc[-252:]
    percentile = float((finestra <= atr_pct.iloc[-1]).mean() * 100)
    vol = "alta" if percentile >= 80 else "bassa" if percentile <= 25 else "normale"
    trend = "negativo" if dist_atr < 0 else "incerto" if dist_atr < L.DIST_MIN_EMA_ATR else "positivo"
    if rsi > L.RSI_TIRATO:
        momento = "tirato"
    elif rsi > L.RSI_MAX:
        momento = "nessuna pausa"
    elif rsi < L.RSI_MIN:
        momento = "caduta forte"
    elif rsi <= float(ieri["RSI"]):
        momento = "pausa in corso"
    else:
        momento = "pausa che finisce"
    supporto = float(df["Low"].iloc[-GIORNI_SUPPORTO:].min())
    resistenza = float(df["High"].iloc[-GIORNI_RESISTENZA - 1:-1].max())
    return {"close": close, "ema": ema, "rsi": rsi, "atr": atr, "dist_atr": dist_atr, "pendenza_ema": pendenza,
            "vol": vol, "vol_percentile": percentile, "trend": trend, "momento": momento,
            "supporto": supporto, "resistenza": resistenza, "colore": u.get("Semaforo", "")}


def metodi_stop(s: dict, capitale_valuta: float, rischio_pct: float) -> list[dict]:
    """Tre modi di mettere lo stop, con prezzo, distanza, quantità per lo stesso rischio, e un giudizio."""
    ingresso, atr = s["close"], s["atr"]
    mult = 2.5 if s["vol"] == "alta" else L.STOP_ATR
    rischio = capitale_valuta * rischio_pct / 100
    candidati = [
        ("atr", f"Volatilità ({_it(mult, 1)} ATR)", ingresso - mult * atr,
         f"Sta {_it(mult, 1)} volte l'escursione media giornaliera sotto l'ingresso: le oscillazioni normali non lo toccano."
         + (" Con la volatilità alta di questi giorni è più largo del solito (2,5 invece di 2)." if mult != L.STOP_ATR else "")),
        ("struttura", "Sotto il minimo recente", s["supporto"] - MARGINE_ATR * atr,
         f"Sta un po' sotto il minimo degli ultimi {GIORNI_SUPPORTO} giorni ({_it(s['supporto'])}). Se il prezzo scende "
         "sotto quel minimo, la pausa è diventata una discesa e l'idea era sbagliata. Il margine evita il punto esatto "
         "in cui si accumulano gli stop di tutti."),
        ("percentuale", f"Percentuale fissa ({_it(STOP_PCT * 100, 0)}%)", ingresso * (1 - STOP_PCT),
         "Comodo ma cieco: non tiene conto di quanto si muove questo mercato. Su un mercato calmo è troppo largo, "
         "su uno agitato troppo stretto."),
    ]
    out = []
    for chiave, nome, stop, perche in candidati:
        distanza = ingresso - stop
        d_atr = distanza / atr if atr else 0
        if distanza <= 0:
            problema = "Non valido: il minimo recente è sopra il prezzo attuale."
        elif d_atr < 1:
            problema = "Troppo stretto: è dentro il rumore di una sola giornata, verrebbe toccato per caso."
        elif d_atr > 4:
            problema = "Molto largo: per rischiare la stessa cifra la quantità diventa piccolissima e l'operazione lentissima."
        else:
            problema = ""
        out.append({"chiave": chiave, "nome": nome, "stop": stop, "distanza": distanza, "distanza_atr": d_atr,
                    "quote": (rischio / distanza) if distanza > 0 else 0.0, "rischio": rischio, "perche": perche,
                    "problema": problema, "consigliato": False})
    # Consigliato: il minimo recente se è a una distanza sensata (1,5-3,5 ATR), altrimenti la volatilità
    strutt = next(m for m in out if m["chiave"] == "struttura")
    scelto = strutt if not strutt["problema"] and 1.5 <= strutt["distanza_atr"] <= 3.5 else out[0]
    scelto["consigliato"] = True
    scelto["motivo_scelta"] = ("Il minimo recente è a una distanza sensata: uno stop sotto la struttura ha un significato "
                               "preciso (l'idea è sbagliata se lo rompe)." if scelto is strutt else
                               "Il minimo recente è troppo vicino o troppo lontano: meglio uno stop basato sulla volatilità.")
    return out


def take_profit(s: dict, stop: dict) -> dict:
    tp = s["close"] + L.RR * stop["distanza"]
    avviso = ""
    if s["close"] < s["resistenza"] < tp:
        avviso = (f"Prima del take profit c'è il massimo degli ultimi {GIORNI_RESISTENZA} giorni ({_it(s['resistenza'])}): "
                  "il prezzo potrebbe rallentare lì. Non spostare il take profit (la ricerca dice che accorciarlo peggiora "
                  "i risultati), ma non stupirti se l'operazione si ferma per un po' a quel livello.")
    return {"tp": tp, "avviso": avviso}


def consigli(s: dict, ricerca_ok: bool) -> tuple[list[str], list[str]]:
    """(cosa fare, cosa non fare) secondo la situazione."""
    fare, non = [], []
    if not ricerca_ok:
        fare.append("Usa questo mercato per <b>allenarti sul Demo</b>: il bot oggi non opera perché la sua ricerca, "
                    "con i costi reali, non trova un vantaggio affidabile.")
    if s["trend"] == "negativo":
        non += ["Comprare <b>perché è sceso tanto</b>: in un trend negativo un prezzo basso può diventare ancora più basso.",
                "Mediare al ribasso (comprare ancora quando scende per abbassare il prezzo medio)."]
        fare += ["Aspettare che il prezzo torni <b>sopra la EMA 200</b> e ci resti.",
                 "Se vuoi esercitarti: osserva come reagisce sui minimi, senza operare."]
    elif s["trend"] == "incerto":
        non.append("Entrare ora: vicino alla EMA 200 i segnali sono spesso falsi, il prezzo la attraversa avanti e indietro.")
        fare.append(f"Aspettare che il prezzo si allontani dalla EMA 200 di almeno 1 ATR (oggi {_it(s['atr'])}).")
    else:
        if s["momento"] == "tirato":
            non.append(f"<b>Inseguire</b> il prezzo: con RSI a {s['rsi']:.0f} è salito tanto e in fretta, spesso poi ritraccia.")
            fare.append(f"Aspettare una pausa: un RSI tra {L.RSI_MIN} e {L.RSI_MAX} ti dà un ingresso più vicino allo stop.")
        elif s["momento"] == "nessuna pausa":
            fare.append(f"Aspettare un ritracciamento: l'ingresso migliore arriva quando l'RSI scende tra {L.RSI_MIN} e {L.RSI_MAX}.")
        elif s["momento"] == "caduta forte":
            non.append("Comprare durante la caduta: RSI sotto 30 vuol dire che i venditori stanno ancora spingendo.")
            fare.append("Aspettare che l'RSI torni sopra 30 e il prezzo smetta di fare nuovi minimi.")
        elif s["momento"] == "pausa in corso":
            fare.append("Tenere d'occhio: la pausa è nella zona giusta, aspetta il primo giorno in cui l'RSI risale.")
            non.append("Anticipare l'ingresso mentre scende ancora: aspettare un giorno costa poco, entrare troppo presto di più.")
        else:
            fare += ["Seguire i 5 passi qui sotto, con <b>stop e take profit impostati subito</b> insieme all'ordine.",
                     "Scrivere nel diario perché entri, prima di premere Compra."]
            non += ["Entrare se il prezzo sul broker è già salito di oltre mezzo ATR: salta l'occasione.",
                    "Allargare lo stop dopo essere entrato: lo stop si decide prima e non si tocca più."]
    if s["vol"] == "alta":
        fare.append("Volatilità <b>alta</b>: rischia meno (0,5% invece dell'1%) e usa uno stop un po' più largo (2,5 ATR).")
        non.append("Operare a ridosso di notizie importanti (banche centrali, dati sul lavoro, trimestrali): i prezzi saltano.")
    elif s["vol"] == "bassa":
        fare.append("Volatilità <b>bassa</b>: i mercati calmi a volte si svegliano all'improvviso, rispetta comunque lo stop.")
    non += ["Aprire un'operazione <b>senza stop loss</b>, anche solo per un minuto.",
            "Usare la quantità proposta dall'app del broker: si calcola sempre in base allo stop e al rischio."]
    return fare, non


ETICHETTE = {
    "trend": {"positivo": ("✅", "Trend positivo"), "incerto": ("⚠️", "Trend incerto"), "negativo": ("⛔", "Trend negativo")},
    "momento": {"tirato": ("⚠️", "Prezzo tirato"), "nessuna pausa": ("⏳", "Nessuna pausa"),
                "caduta forte": ("⛔", "Caduta forte"), "pausa in corso": ("⏳", "Pausa in corso"),
                "pausa che finisce": ("✅", "Pausa che finisce")},
    "vol": {"alta": ("🌪️", "Volatilità alta"), "normale": ("🌤️", "Volatilità normale"), "bassa": ("🌙", "Volatilità bassa")},
}
