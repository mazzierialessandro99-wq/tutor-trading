"""
SENTINELLA — l'assistente che sorveglia i mercati 24 ore su 24 e ti scrive su Telegram.

Gira da sola su GitHub ogni 30 minuti (vedi .github/workflows/sentinella.yml).
Applica le stesse regole del semaforo della dashboard e ti avvisa quando:
  • un mercato DIVENTA verde  -> messaggio con i numeri dell'operazione già calcolati
  • un mercato che era verde non lo è più
  • ogni mattina alle 8 (ora italiana) -> riepilogo della giornata
NON invia ordini: gli ordini li metti tu, a mano, sul conto demo.

Prove dal PC:
    python sentinella.py --prova        manda subito un messaggio di prova con il riepilogo
    python sentinella.py --a-secco      stampa i messaggi invece di mandarli (nessun Telegram)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import logica as L

ROMA = ZoneInfo("Europe/Rome")
APP_URL = os.environ.get("APP_URL", "https://tutor-trading-ale.streamlit.app")
STATO_FILE = Path(os.environ.get("STATO_FILE", "stato_sentinella.json"))
PIANO = L.carica_piano()                                 # il tuo piano personale (piano.json)
CAPITALE = float(os.environ.get("CAPITALE") or PIANO.get("capitale", 1000))   # in euro
RISCHIO = float(os.environ.get("RISCHIO") or PIANO.get("rischio_per_operazione", 1))  # % per operazione
DALLE, ALLE = PIANO.get("orari_avvisi", ["00:00", "23:59"])
ORA_RIEPILOGO = int(os.environ.get("ORA_RIEPILOGO", "8"))
DEMO = os.environ.get("TUTOR_DEMO") == "1"               # dati inventati, solo per prove senza internet

EMOJI = {"VERDE": "🟢", "GIALLO": "🟡", "ROSSO": "🔴"}


# ------------------------------------------------------------------------------
# FORMATI ITALIANI
# ------------------------------------------------------------------------------
def num(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def prezzo(p: float, valuta: str) -> str:
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta)
    return f"{num(p, 4 if abs(p) < 10 else 2)} {sim}"


def quote(q: float) -> str:
    return num(q, 0 if q >= 100 else 2 if q >= 1 else 4)


# ------------------------------------------------------------------------------
# DATI
# ------------------------------------------------------------------------------
def _demo(ticker: str) -> pd.DataFrame:
    rng = np.random.default_rng(sum(map(ord, ticker)))
    n = 600
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0007, 0.012, n)))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.004,
                         "Low": np.minimum(op, close) * 0.996, "Close": close}, index=idx)


def scarica_tutti(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Candele giornaliere degli ultimi 2 anni per tutti i mercati, in una sola richiesta."""
    if DEMO:
        return {t: _demo(t) for t in tickers}
    import yfinance as yf
    grezzi = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, progress=False,
                         group_by="ticker", threads=True)
    dati = {}
    for t in tickers:
        try:
            df = grezzi[t][["Open", "High", "Low", "Close"]].dropna()
            df.index = pd.to_datetime(df.index).tz_localize(None)
            if len(df) > L.EMA_PERIODO + 20:
                dati[t] = df
        except Exception:
            continue
    return dati


# ------------------------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------------------------
def invia(testo: str, a_secco: bool = False):
    if a_secco:
        print("─" * 60 + "\n" + testo + "\n")
        return
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        sys.exit("Mancano TELEGRAM_TOKEN o TELEGRAM_CHAT_ID (vanno nei Secrets di GitHub).")
    dati = urllib.parse.urlencode({"chat_id": chat, "text": testo, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dati, timeout=20) as r:
            r.read()
    except urllib.error.HTTPError as e:
        # Il token non viene mai stampato
        sys.exit(f"Telegram ha rifiutato il messaggio ({e.code}): controlla il token e di aver premuto Avvia sul bot.")


# ------------------------------------------------------------------------------
# MESSAGGI
# ------------------------------------------------------------------------------
def msg_verde(nome: str, ticker: str, valuta: str, v: dict, p: dict, cambio: float, rischio: float) -> str:
    eur = lambda x: num(x / cambio)
    dec = 4 if p["ingresso"] < 10 else 2
    return (
        f"🟢 <b>{nome}</b>: semaforo <b>VERDE</b>\n"
        f"Trend positivo (sopra la EMA 200) e RSI a {v['rsi']:.0f} in risalita: il ritracciamento sta finendo.\n\n"
        f"📋 <b>Su Capital.com</b> (Demo · piano {num(CAPITALE, 0)} € · rischio {num(rischio, 2).rstrip('0').rstrip(',')}%)\n"
        f"Cerca <b>{L.nome_capital(ticker, nome)}</b> → Compra\n"
        f"• Quantità (Contratti): <b>{quote(p['quote'])}</b>  ← cancella quella proposta!\n"
        f"• Acquista quando il prezzo è pari a: <b>{prezzo(p['ingresso'], valuta)}</b>\n"
        f"• Stop-loss: <b>{num(p['distanza'], dec)} punti</b> sotto l'ingresso (≈ {prezzo(p['stop'], valuta)})\n"
        f"• Take profit: <b>{num(p['distanza'] * L.RR, dec)} punti</b> sopra (≈ {prezzo(p['tp'], valuta)})\n"
        f"Rischi circa {eur(p['perdita'])} € per guadagnarne circa {eur(p['guadagno'])} €.\n\n"
        f"⚠️ Controlla il prezzo vero sull'app: se è già sopra {prezzo(p['ingresso'] + 0.5 * v['atr'], valuta)}, "
        f"non inseguirlo.\n"
        f"👉 Il perché e il grafico: {APP_URL}"
    )


def msg_non_piu_verde(nome: str, colore: str) -> str:
    return (f"⚪ <b>{nome}</b> non è più verde (ora {EMOJI[colore]} {colore.lower()}).\n"
            "Se non sei entrato, lascia stare. Se sei dentro, non toccare nulla: decidono Stop Loss e Take Profit.")


def msg_riepilogo(righe: list[dict], titolo: str) -> str:
    ordine = {"VERDE": 0, "GIALLO": 1, "ROSSO": 2}
    righe = sorted(righe, key=lambda r: (ordine[r["colore"]], r["nome"]))
    n = {c: sum(r["colore"] == c for r in righe) for c in ordine}
    testa = (f"{titolo}\n"
             f"{EMOJI['VERDE']} {n['VERDE']}   {EMOJI['GIALLO']} {n['GIALLO']}   {EMOJI['ROSSO']} {n['ROSSO']}\n")
    if n["VERDE"]:
        verdi = ", ".join(f"<b>{r['nome']}</b>" for r in righe if r["colore"] == "VERDE")
        testa += f"\nOccasioni da guardare: {verdi}\n"
    else:
        testa += "\nNessuna occasione oggi: si aspetta. Anche questo è trading. 🧘\n"
    elenco = "\n".join(f"{EMOJI[r['colore']]} {r['nome']} · RSI {r['rsi']:.0f}" for r in righe)
    return f"{testa}\n{elenco}\n\n👉 {APP_URL}"


# ------------------------------------------------------------------------------
# GIRO DI CONTROLLO
# ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="manda subito un messaggio di prova")
    ap.add_argument("--a-secco", action="store_true", help="stampa i messaggi invece di mandarli")
    args = ap.parse_args()

    stato = json.loads(STATO_FILE.read_text()) if STATO_FILE.exists() else {}
    primo_giro = not stato
    stato.setdefault("asset", {})
    ora = datetime.now(ROMA)
    oggi = ora.date().isoformat()

    tickers = [t for t, _ in L.ASSET.values()]
    dati = scarica_tutti(tickers + ["EURUSD=X"])
    if not dati:
        sys.exit("Nessun dato scaricato (Yahoo non risponde): riprovo al prossimo giro.")
    eurusd = 1.08 if DEMO or "EURUSD=X" not in dati else float(dati["EURUSD=X"]["Close"].iloc[-1])

    righe, messaggi = [], []
    in_orario = DALLE <= f"{ora:%H:%M}" <= ALLE
    esclusi = set(PIANO.get("mercati_esclusi", []))
    for nome, (ticker, valuta) in L.ASSET.items():
        if ticker not in dati or nome in esclusi or ticker in esclusi:
            continue
        v = L.valuta(L.aggiungi_indicatori(dati[ticker]))
        righe.append({"nome": nome, "colore": v["colore"], "rsi": v["rsi"]})
        prima = stato["asset"].get(ticker, {})
        cambio = 1.0 if valuta == "EUR" else eurusd

        if not in_orario and not primo_giro:
            continue    # fuori dagli orari del piano: niente avvisi, ne riparliamo al mattino
        if not primo_giro and v["colore"] == "VERDE" and prima.get("colore") != "VERDE" \
                and prima.get("avvisato") != oggi:
            rischio = L.rischio_per(ticker, PIANO, RISCHIO)
            p = L.piano(CAPITALE * cambio, rischio, v["close"], v["atr"])
            messaggi.append(msg_verde(nome, ticker, valuta, v, p, cambio, rischio))
            prima["avvisato"] = oggi
        elif not primo_giro and prima.get("colore") == "VERDE" and v["colore"] != "VERDE":
            messaggi.append(msg_non_piu_verde(nome, v["colore"]))
        if in_orario or primo_giro:
            prima["colore"] = v["colore"]
            stato["asset"][ticker] = prima

    if args.prova or primo_giro:
        messaggi.insert(0, msg_riepilogo(
            righe, "👋 <b>Ciao! Sono il tuo Tutor di Trading.</b>\n"
                   "Controllo i mercati ogni 30 minuti, giorno e notte, e ti scrivo quando un semaforo diventa verde. "
                   "Non invio mai ordini: decidi sempre tu.\n\n<b>La situazione adesso:</b>"))
    elif ora.hour >= ORA_RIEPILOGO and stato.get("riepilogo") != oggi:
        messaggi.insert(0, msg_riepilogo(righe, f"☀️ <b>Buongiorno! Il semaforo di oggi</b> ({ora:%d/%m})"))
    if ora.hour >= ORA_RIEPILOGO:
        stato["riepilogo"] = oggi

    for m in messaggi:
        invia(m, args.a_secco)
    stato["ultimo_giro"] = ora.isoformat(timespec="minutes")
    STATO_FILE.write_text(json.dumps(stato, indent=1, ensure_ascii=False))
    print(f"Giro completato: {len(righe)} mercati controllati, {len(messaggi)} messaggi.")


if __name__ == "__main__":
    main()
