"""
SENTINELLA — l'assistente che sorveglia i mercati 24 ore su 24 e ti scrive su Telegram.

Gira da sola su GitHub ogni 30 minuti (vedi .github/workflows/sentinella.yml).
Applica le regole del semaforo e il tuo piano (piano.json):
  • quando un mercato DIVENTA verde:
      - modalità automatica (solo conto DEMO Capital.com): apre l'operazione con stop e take profit e ti avvisa
      - altrimenti: ti scrive cosa fare, con i numeri già calcolati
  • quando un'operazione si chiude (stop o take profit) -> ti dice com'è andata
  • se raggiungi un limite di perdita del piano -> si ferma da sola
  • ogni mattina alle 8 (ora italiana) -> riepilogo della giornata
Comandi su Telegram (letti a ogni giro): /stop  /riprendi  /stato  /resoconto
Ogni lunedì mattina: resoconto della settimana (operazioni, risultati, confronto con il backtest).

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import backtest as BT
import capital as C
import eventi as E
import trend_mensile as TM
import logica as L
import ricerca as R

ROMA = ZoneInfo("Europe/Rome")
APP_URL = os.environ.get("APP_URL", "https://tutor-trading-ale.streamlit.app")
STATO_FILE = Path(os.environ.get("STATO_FILE", "stato_sentinella.json"))
PIANO = L.carica_piano()                                 # il tuo piano personale (piano.json)
CAPITALE = float(os.environ.get("CAPITALE") or PIANO.get("capitale", 1000))   # in euro
RISCHIO = float(os.environ.get("RISCHIO") or PIANO.get("rischio_per_operazione", 1))  # % per operazione
DALLE, ALLE = PIANO.get("orari_avvisi", ["00:00", "23:59"])
MAX_APERTE = int(PIANO.get("max_posizioni_aperte", 3))
OBIETTIVO = float(PIANO.get("obiettivo", 0) or 0)       # es. 1000: dove vuoi arrivare partendo da CAPITALE
AUTOMATICO = PIANO.get("modalita") == "automatico"
ORA_RIEPILOGO = int(os.environ.get("ORA_RIEPILOGO", "8"))
DEMO = os.environ.get("TUTOR_DEMO") == "1"               # dati inventati, solo per prove senza internet
BROKER_SIMULATO = os.environ.get("BROKER_SIMULATO") == "1"   # conto finto, solo per prove

EMOJI = {"VERDE": "🟢", "GIALLO": "🟡", "ROSSO": "🔴"}

# ESITO DELLA RICERCA SETTIMANALE: decide SE e COME il bot opera (file scaricato dal branch "dati")
RICERCA_FILE = Path(os.environ.get("RICERCA_FILE", "ricerca_esito.json"))
RICERCA = json.loads(RICERCA_FILE.read_text()) if RICERCA_FILE.exists() else None
CFG = (RICERCA or {}).get("vincitrice")          # None = nessuna regola promossa: non si apre niente
# PALESTRA (solo Demo): se la ricerca non promuove niente, il bot opera comunque la strategia di base
# per raccogliere risultati veri da confrontare con il backtest. Ogni operazione è segnata come esperimento.
PALESTRA = bool(PIANO.get("palestra"))
GIORNI_MAX = 84                                     # 60 giorni di borsa, come nel backtest
TREND = PIANO.get("trend_mensile") or {}          # {"attivo": true, "capitale": 50000}
if not CFG and PALESTRA:
    CFG = {"strategia": "ritracciamento", "rr": 2.0, "pareggio": False, "filtro": "sempre", "palestra": True}
if CFG:
    L.RR = float(CFG.get("rr", L.RR))
NOMI_FILTRO = {"sempre": "sempre", "trend": "solo con il mercato USA in trend positivo",
               "trend+calmo": "solo con mercato USA in trend positivo e volatilità normale",
               "fiducia": "solo quando le ultime 20 occasioni studiate hanno reso",
               "trend+fiducia": "con mercato USA in trend positivo e ultime occasioni in guadagno"}
NOMI_STRATEGIA = {"ritracciamento": "ritracciamento in trend (EMA 200 + RSI)",
                  "rottura": "rottura dei massimi a 55 giorni"}


def descrizione_ricerca() -> str:
    if CFG and CFG.get("palestra"):
        data = str((RICERCA or {}).get("data", ""))[:10] or "—"
        return (f"🧪 <b>Palestra sul Demo</b>: la ricerca del {data} non promuove nessuna regola, ma qui opero lo stesso "
                "la strategia di base (ritracciamento, 1:2) per studiare il mercato dal vivo. Ogni operazione è un esperimento.")
    if not RICERCA:
        return "🔬 Ricerca: non ancora disponibile, quindi non apro operazioni."
    data = str(RICERCA.get("data", ""))[:10]
    if not CFG:
        return (f"🔬 Ricerca del {data}: nessuna regola ha un vantaggio affidabile (anche sui mercati mai visti), "
                "quindi <b>non apro nuove operazioni</b>. Continuo a studiare e ricontrollo domenica.")
    mv = CFG.get("mai_visti", {})
    return (f"🔬 Ricerca del {data}: strategia attiva <b>{NOMI_STRATEGIA.get(CFG['strategia'], CFG['strategia'])}</b>, "
            f"take profit 1:{CFG['rr']:.0f}{', stop a pareggio' if CFG.get('pareggio') else ''}, "
            f"{NOMI_FILTRO.get(CFG['filtro'], CFG['filtro'])} (sui mercati mai visti: profit factor {mv.get('profit_factor', 0):.2f}).")


# ------------------------------------------------------------------------------
# FORMATI ITALIANI
# ------------------------------------------------------------------------------
def num(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def prezzo(p: float, valuta: str = "") -> str:
    sim = {"USD": "$", "EUR": "€"}.get(valuta, valuta)
    return f"{num(p, 4 if abs(p) < 10 else 2)} {sim}".strip()


def quote(q: float) -> str:
    return num(q, 0 if q >= 100 else 2 if q >= 1 else 4)


def pct(x: float) -> str:
    return num(x, 2).rstrip("0").rstrip(",")


def euro(x: float) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{num(abs(x))} €"


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


def scarica_tutti(tickers: list[str], periodo: str = "2y", intervallo: str = "1d") -> dict[str, pd.DataFrame]:
    """Candele di tutti i mercati (giornaliere salvo diversa indicazione), in una sola richiesta."""
    if DEMO:
        return {t: _demo(t) for t in tickers}
    import yfinance as yf
    grezzi = yf.download(tickers, period=periodo, interval=intervallo, auto_adjust=True, progress=False,
                         group_by="ticker", threads=True)
    dati = {}

    def pulisci(df) -> pd.DataFrame | None:
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df if len(df) > L.EMA_PERIODO + 20 else None

    for t in tickers:
        try:
            df = pulisci(grezzi[t].copy())
            if df is not None:
                dati[t] = df
        except Exception:
            continue
    # Riprova uno alla volta i mercati che non sono arrivati (a volte Yahoo ne perde qualcuno)
    for t in [t for t in tickers if t not in dati]:
        try:
            df = pulisci(yf.download(t, period=periodo, interval=intervallo, auto_adjust=True, progress=False))
            if df is not None:
                dati[t] = df
        except Exception:
            continue
    return dati


# ------------------------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------------------------
def _telegram(metodo: str, parametri: dict) -> dict:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        sys.exit("Manca TELEGRAM_TOKEN (va nei Secrets di GitHub).")
    dati = urllib.parse.urlencode(parametri).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{metodo}", dati, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Il token non viene mai stampato
        sys.exit(f"Telegram ha rifiutato la richiesta ({e.code}): controlla il token e di aver premuto Avvia sul bot.")


def invia(testo: str, a_secco: bool = False, silenzioso: bool = False):
    if a_secco:
        print("─" * 60 + "\n" + testo + "\n")
        return
    _telegram("sendMessage", {"chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""), "text": testo,
                              "parse_mode": "HTML", "disable_web_page_preview": "true",
                              "disable_notification": "true" if silenzioso else "false"})


def leggi_comandi(stato: dict, a_secco: bool) -> list[str]:
    """Comandi che hai scritto al bot dall'ultimo giro (solo dalla tua chat)."""
    if a_secco:
        return [c for c in os.environ.get("COMANDI_PROVA", "").split(",") if c]
    risposta = _telegram("getUpdates", {"offset": stato.get("telegram_offset", 0), "timeout": 0})
    comandi, chat = [], str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    for u in risposta.get("result", []):
        stato["telegram_offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) == chat and m.get("text", "").startswith("/"):
            comandi.append(m["text"].split()[0].split("@")[0].lower())
    return comandi


# ------------------------------------------------------------------------------
# MESSAGGI
# ------------------------------------------------------------------------------
def msg_verde(nome: str, ticker: str, valuta: str, v: dict, p: dict, cambio: float, rischio: float,
              motivo: str = "") -> str:
    eur = lambda x: num(x / cambio)
    dec = 4 if p["ingresso"] < 10 else 2
    testa = f"🟢 <b>{nome}</b>: semaforo <b>VERDE</b>\n"
    if motivo:
        testa += f"ℹ️ Non l'ho aperta da solo: {motivo}\n"
    return (
        testa +
        f"Trend positivo (sopra la EMA 200) e RSI a {v['rsi']:.0f} in risalita: il ritracciamento sta finendo.\n\n"
        f"📋 <b>Su Capital.com</b> (Demo · piano {num(CAPITALE, 0)} € · rischio {pct(rischio)}%)\n"
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


def msg_aperta(nome: str, m: dict, op: dict, v: dict, rischio_eur: float, aperte: int) -> str:
    return (
        f"✅ <b>Ho aperto {nome}</b> sul conto Demo" + (" · 🧪 esperimento (palestra)" if CFG and CFG.get("palestra") else "") + "\n"
        f"Comprati <b>{quote(op['size'])}</b> contratti a <b>{prezzo(op['livello'], m['valuta'])}</b>\n"
        f"Stop-loss <b>{prezzo(op['stop'], m['valuta'])}</b> · Take profit <b>{prezzo(op['tp'], m['valuta'])}</b>\n"
        f"Rischio ≈ {num(rischio_eur)} € · obiettivo ≈ {num(rischio_eur * L.RR)} €\n\n"
        f"Perché: {'il prezzo ha superato il massimo degli ultimi 55 giorni, con trend positivo' if CFG and CFG['strategia'] == 'rottura' else 'trend positivo e RSI a ' + format(v['rsi'], '.0f') + ' in risalita dopo una pausa'}.\n"
        f"Posizioni aperte: {aperte}/{MAX_APERTE}. Per fermarmi scrivi /stop"
    )


def msg_non_piu_verde(nome: str, colore: str, auto: bool) -> str:
    fine = ("Se c'è un'operazione aperta la lascio lavorare: decidono Stop-loss e Take profit."
            if auto else
            "Se non sei entrato, lascia stare. Se sei dentro, non toccare nulla: decidono Stop-loss e Take profit.")
    return f"⚪ <b>{nome}</b> non è più verde (ora {EMOJI[colore]} {colore.lower()}).\n{fine}"


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
# CONTO: risultati per periodo e limiti di perdita del piano
# ------------------------------------------------------------------------------
LIMITI = [("giorno", "stop_giornaliero_pct", "del giorno", "fino a domani"),
          ("settimana", "stop_settimanale_pct", "della settimana", "fino a lunedì"),
          ("mese", "stop_mensile_pct", "del mese", "fino al mese prossimo: rivediamo insieme il piano")]


def chiavi_periodo(ora: datetime) -> dict:
    anno, sett, _ = ora.isocalendar()
    return {"giorno": ora.date().isoformat(), "settimana": f"{anno}-W{sett:02d}", "mese": f"{ora:%Y-%m}"}


def aggiorna_periodi(stato: dict, valore: float, ora: datetime) -> dict:
    """Ricorda il valore del conto all'inizio di giorno/settimana/mese e restituisce il risultato di ciascuno."""
    per = stato.setdefault("periodi", {})
    risultati = {}
    for nome, chiave in chiavi_periodo(ora).items():
        if per.get(nome, {}).get("chiave") != chiave:
            if nome in per:
                per[nome + "_prec"] = {"chiave": per[nome]["chiave"], "risultato": valore - per[nome]["inizio"]}
            per[nome] = {"chiave": chiave, "inizio": valore}
        risultati[nome] = valore - per[nome]["inizio"]
    return risultati


def limite_superato(risultati: dict) -> tuple[str, str, float] | None:
    for nome, campo, testo, fino in LIMITI:
        soglia = CAPITALE * float(PIANO.get(campo, 100)) / 100
        if risultati.get(nome, 0) <= -soglia:
            return nome, f"limite di perdita {testo} raggiunto ({euro(risultati[nome])}, soglia −{num(soglia)} €)", soglia
    return None


def progresso(stato: dict, valore_conto: float) -> float:
    """Capitale 'virtuale' del piano: parte da CAPITALE e si muove con i risultati del bot sul Demo."""
    ob = stato.get("obiettivo_traccia")
    if not ob or ob.get("capitale") != CAPITALE:
        ob = stato["obiettivo_traccia"] = {"capitale": CAPITALE, "base": valore_conto, "tappe": []}
    return CAPITALE + (valore_conto - ob["base"])


def barra(attuale: float) -> str:
    if not OBIETTIVO or OBIETTIVO <= CAPITALE:
        return ""
    quota = max(0.0, min(1.0, (attuale - CAPITALE) / (OBIETTIVO - CAPITALE)))
    pieni = round(quota * 10)
    return f"🎯 Obiettivo: {num(attuale, 0)} € / {num(OBIETTIVO, 0)} €  {'▰' * pieni}{'▱' * (10 - pieni)} {quota * 100:.0f}%"


# Valori attesi dal backtest reale (3 anni, 20 mercati): servono per il confronto nel resoconto
ATTESO = {"win_rate": 43.0, "profit_factor": 1.31, "operazioni_settimana": 0.6}
MIN_OPERAZIONI_GIUDIZIO = 30


def utc_str(iso_locale: str) -> str:
    try:
        return datetime.fromisoformat(iso_locale).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return ""


def risultato_chiusura(broker, epic: str, aperta_iso: str) -> float | None:
    """Guadagno/perdita in euro di un'operazione chiusa, letto dallo storico di Capital.com."""
    try:
        da = utc_str(aperta_iso)
        movimenti = [t for t in broker.transazioni(5)
                     if t.get("transactionType") == "TRADE" and t.get("instrumentName") == epic
                     and str(t.get("dateUtc") or t.get("date") or "")[:16] >= da]
        if not movimenti:
            return None
        return sum(float(str(t.get("size", "0")).replace(",", "")) for t in movimenti)
    except Exception:
        return None


def statistiche(chiuse: list[dict]) -> dict:
    vals = [c["euro"] for c in chiuse if c.get("euro") is not None]
    vinte = [v for v in vals if v > 0]
    perse = [v for v in vals if v <= 0]
    return {"n": len(vals), "vinte": len(vinte), "totale": sum(vals),
            "win_rate": len(vinte) / len(vals) * 100 if vals else 0.0,
            "profit_factor": sum(vinte) / -sum(perse) if perse and sum(perse) else (float("inf") if vinte else 0.0),
            "media_vinta": sum(vinte) / len(vinte) if vinte else 0.0,
            "media_persa": sum(perse) / len(perse) if perse else 0.0}


def msg_resoconto(stato: dict, titolo: str, risultato_periodo: float | None, giorni: int,
                  posizioni: list[dict], attuale: float | None) -> str:
    da = (datetime.now(ROMA) - timedelta(days=giorni)).isoformat()
    chiuse_tutte = stato.get("chiuse", [])
    chiuse = [c for c in chiuse_tutte if c.get("chiusa", "") >= da]
    aperte_periodo = [r for r in stato.get("registro", []) if r.get("data", "") >= da]
    righe = [titolo]
    if risultato_periodo is not None:
        righe.append(f"Risultato del bot: <b>{euro(risultato_periodo)}</b>")
    if attuale is not None and OBIETTIVO:
        righe.append(barra(attuale))
    righe.append(f"\n📥 Operazioni aperte: {len(aperte_periodo)}" +
                 (" (" + ", ".join(r["nome"] for r in aperte_periodo) + ")" if aperte_periodo else ""))
    if chiuse:
        righe.append(f"📤 Operazioni chiuse: {len(chiuse)}")
        righe += [f"   {'✅' if (c.get('euro') or 0) > 0 else '❌'} {c['nome']}: "
                  f"{euro(c['euro']) if c.get('euro') is not None else 'risultato non disponibile'}" for c in chiuse]
    else:
        righe.append("📤 Operazioni chiuse: nessuna")
    if posizioni:
        righe.append(f"⏳ Ancora aperte: " + ", ".join(f"{p['nome']} ({euro(float(p.get('upl') or 0))})" for p in posizioni))
    giri = stato.get("giri", {}).get(chiavi_periodo(datetime.now(ROMA))["settimana"], 0)
    if giri:
        righe.append(f"🛰️ Controlli dei mercati questa settimana: {giri} (ne servono circa 48 al giorno)")

    righe.append("\n" + descrizione_ricerca())
    st = statistiche(chiuse_tutte)
    righe.append(f"\n📚 <b>Dall'inizio</b>: {st['n']} operazioni chiuse · totale {euro(st['totale'])}")
    if st["n"]:
        righe.append(f"Vinte {st['vinte']}/{st['n']} ({st['win_rate']:.0f}%, atteso circa {ATTESO['win_rate']:.0f}%) · "
                     f"media vinta {euro(st['media_vinta'])} · media persa {euro(st['media_persa'])}")
    if st["n"] < MIN_OPERAZIONI_GIUDIZIO:
        righe.append(f"🧪 Per giudicare le regole servono almeno {MIN_OPERAZIONI_GIUDIZIO} operazioni chiuse: siamo a "
                     f"{st['n']}/{MIN_OPERAZIONI_GIUDIZIO}. Fino ad allora non cambio niente: sarebbe imparare dal caso.")
    elif st["win_rate"] < ATTESO["win_rate"] - 10 or st["profit_factor"] < 1:
        righe.append("⚠️ I risultati dal vivo sono <b>sotto</b> quelli del backtest. È il momento di una revisione: "
                     "scrivimelo in chat e verifichiamo insieme le correzioni sul backtest prima di applicarle.")
    else:
        righe.append("👍 I risultati dal vivo sono in linea con il backtest: le regole restano così.")
    righe.append(f"\n👉 {APP_URL}")
    return "\n".join(righe)


def msg_stato(auto_attivo: bool, conto: dict | None, risultati: dict | None, posizioni: list[dict],
              attuale: float | None = None) -> str:
    righe = [f"📊 <b>Stato dell'assistente</b>",
             f"Modalità: {'🤖 automatica (Demo)' if auto_attivo else '✋ solo avvisi' if not AUTOMATICO else '⏸️ in pausa (/riprendi per ripartire)'}"]
    righe.append(descrizione_ricerca())
    if attuale is not None and OBIETTIVO:
        righe.append(barra(attuale))
    if conto:
        righe.append(f"Saldo demo (tutto il conto): {num(conto['saldo'])} € · aperto: {euro(conto['pl_aperto'])}")
    if risultati:
        for nome, campo, testo, _ in LIMITI:
            righe.append(f"Risultato {testo}: {euro(risultati[nome])} (limite −{num(CAPITALE * float(PIANO.get(campo, 100)) / 100)} €)")
    if posizioni:
        righe.append(f"\nPosizioni aperte ({len(posizioni)}/{MAX_APERTE}):")
        righe += [f"• {p['nome']}: {quote(float(p['size']))} @ {prezzo(float(p['livello']))} · {euro(float(p.get('upl') or 0))}"
                  for p in posizioni]
    elif conto:
        righe.append("\nNessuna posizione aperta.")
    righe.append(f"\nComandi: /stato · /resoconto · /stop · /riprendi\n👉 {APP_URL}")
    return "\n".join(righe)


# ------------------------------------------------------------------------------
# ESECUZIONE AUTOMATICA (solo DEMO)
# ------------------------------------------------------------------------------
def prova_ad_aprire(broker, ticker: str, nome: str, v: dict, eurusd: float, posizioni: list[dict],
                    fattore_rischio: float = 1.0) -> tuple[dict | None, str]:
    """Apre un acquisto rispettando il piano. Restituisce (operazione, motivo se non aperta)."""
    if len(posizioni) >= MAX_APERTE:
        return None, f"ci sono già {len(posizioni)} operazioni aperte (massimo {MAX_APERTE} nel tuo piano)"
    m = broker.trova(ticker, nome)
    if not m:
        return None, "non ho trovato lo strumento su Capital.com"
    if any(p["epic"] == m["epic"] for p in posizioni):
        return None, "c'è già un'operazione aperta su questo mercato"
    if not m["aperto"]:
        return None, "il mercato su Capital.com in questo momento è chiuso"
    if m["valuta"] not in ("EUR", "USD"):
        return None, f"lo strumento è in {m['valuta']}, valuta che non gestisco ancora"

    ingresso = m["offer"]
    if not (0.85 < ingresso / v["close"] < 1.15):
        return None, "il prezzo su Capital.com è troppo diverso dal nostro: preferisco non rischiare"
    if ingresso > v["close"] + 0.5 * v["atr"]:
        return None, "il prezzo è già salito troppo: non inseguo il mercato"

    distanza = L.STOP_ATR * v["atr"]
    if m["min_distanza_stop"] and distanza < m["min_distanza_stop"]:
        return None, "lo stop richiesto è più vicino del minimo consentito da Capital.com"
    cambio = 1.0 if m["valuta"] == "EUR" else eurusd
    rischio_pct = L.rischio_per(ticker, PIANO, RISCHIO) * fattore_rischio
    rischio_eur = CAPITALE * rischio_pct / 100
    size = C.arrotonda_size(rischio_eur * cambio / distanza, m["passo"])
    if size < m["min_size"]:
        minimo = m["min_size"] * distanza / cambio
        return None, (f"la quantità minima ({quote(m['min_size'])}) farebbe rischiare {num(minimo)} €, "
                      f"più del {pct(rischio_pct)}% del tuo piano")
    size = min(size, m["max_size"])
    rischio_vero = size * distanza / cambio
    if rischio_vero > CAPITALE * 0.02 + 0.01:      # cintura di sicurezza: mai oltre il 2%
        return None, "il rischio calcolato supera il 2% del capitale: blocco di sicurezza"

    dec = 5 if ingresso < 10 else 2
    stop, tp = round(ingresso - distanza, dec), round(ingresso + L.RR * distanza, dec)
    esito = broker.compra(m["epic"], size, stop, tp)
    op = {"epic": m["epic"], "nome": nome, "dealId": esito.get("dealId"), "size": esito.get("size", size),
          "livello": esito.get("livello") or ingresso, "stop": stop, "tp": tp, "rischio_eur": rischio_vero,
          "valuta": m["valuta"], "distanza": distanza}
    return op, ""


def fiducia_ok(dati: dict, stato: dict, oggi: str) -> bool:
    """Le ultime 20 occasioni 'studiate' (tutte, prese o no) hanno reso? Calcolato una volta al giorno."""
    f = stato.get("fiducia", {})
    if f.get("data") == oggi:
        return bool(f.get("ok"))
    studiate = []
    for nome, (t, _) in L.mercati(PIANO).items():
        if t not in dati:
            continue
        df = BT.segnali_mercato(dati[t])
        for i in R.segnali(df, CFG["strategia"]):
            if i >= L.EMA_PERIODO and df.index[i] >= df.index[-1] - pd.Timedelta(days=365):
                o = R.simula(df, i, float(CFG["rr"]), bool(CFG.get("pareggio")), t)
                if o:
                    studiate.append(o)
    studiate.sort(key=lambda o: o["uscita"])
    ultime = [o["R"] for o in studiate][-R.FIDUCIA_N:]
    ok = len(ultime) >= R.FIDUCIA_N and float(np.mean(ultime)) > 0
    stato["fiducia"] = {"data": oggi, "ok": ok, "media_R": round(float(np.mean(ultime)), 3) if ultime else None}
    return ok


def permesso_cfg(dati: dict, stato: dict, oggi: str) -> tuple[bool, str]:
    """Il filtro della strategia attiva permette di operare oggi?"""
    filtro = CFG.get("filtro", "sempre")
    if filtro in ("trend", "trend+calmo", "trend+fiducia"):
        if "^GSPC" not in dati:
            return False, "mancano i dati dell'S&P 500 per decidere"
        reg = R.regime(dati["^GSPC"])
        domani = dati["^GSPC"].index[-1] + pd.Timedelta(days=1)
        if not R.permesso(reg, domani, "trend+calmo" if filtro == "trend+calmo" else "trend"):
            return False, ("il mercato USA non è in trend positivo o è troppo agitato" if filtro == "trend+calmo"
                           else "il mercato USA non è in trend positivo")
    if "fiducia" in filtro and not fiducia_ok(dati, stato, oggi):
        return False, "le ultime 20 occasioni studiate non hanno reso: aspetto che il mercato torni favorevole"
    return True, ""


def gestisci_pareggio(broker, stato: dict, posizioni: list[dict], messaggi: list[str]):
    """Stop spostato al prezzo d'ingresso quando l'operazione guadagna quanto rischiava."""
    for p in posizioni:
        info = stato.get("aperte", {}).get(p.get("dealId"), {})
        livello, distanza = info.get("livello"), info.get("distanza")
        if not livello or not distanza or info.get("pareggio_fatto") or p.get("bid") is None:
            continue
        if float(p["bid"]) >= float(livello) + float(distanza) and float(p.get("stop") or 0) < float(livello):
            try:
                broker.sposta_stop(p["dealId"], float(livello), p.get("tp"))
                info["pareggio_fatto"] = True
                messaggi.append(f"🛡️ <b>{info.get('nome', p.get('nome'))}</b>: guadagna già quanto rischiava, "
                                f"ho spostato lo stop-loss al prezzo d'ingresso. Da ora, nel peggiore dei casi, esce a zero.")
            except C.CapitalErrore as e:
                print(f"Stop a pareggio non riuscito su {p.get('nome')}: {e}")


def annota(stato: dict, ora: datetime, mercato: str, decisione: str, motivo: str, icona: str = "•"):
    """Diario delle decisioni del bot (lo mostra l'app nella sezione Bot)."""
    stato.setdefault("decisioni", []).append({"ora": ora.isoformat(timespec="minutes"), "mercato": mercato,
                                              "decisione": decisione, "motivo": motivo, "icona": icona})
    stato["decisioni"] = stato["decisioni"][-150:]


def collega_broker():
    if BROKER_SIMULATO:
        return C.CapitalSimulato(saldo=float(os.environ.get("SALDO_SIMULATO", "1000")))
    if not C.credenziali_presenti():
        return None
    return C.CapitalDemo()


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
    in_orario = DALLE <= f"{ora:%H:%M}" <= ALLE
    messaggi: list[str] = []

    # ---- 1. comandi da Telegram ----
    comandi = leggi_comandi(stato, args.a_secco)
    if "/stop" in comandi:
        stato["pausa"] = True
        messaggi.append("⏸️ <b>Fermato.</b> Non apro nuove operazioni (quelle aperte restano con i loro stop). "
                        "Continuo a mandarti gli avvisi. Scrivi /riprendi per ripartire.")
    if "/riprendi" in comandi or "/start" in comandi:
        if stato.get("pausa"):
            messaggi.append("▶️ <b>Ripartito.</b> Riprendo a operare sul conto Demo seguendo il tuo piano.")
        stato["pausa"] = False

    # ---- 2. prezzi e semafori ----
    tickers = [t for t, _ in L.mercati(PIANO).values()]
    dati = scarica_tutti(tickers + ["EURUSD=X", "^VIX"] + (["^GSPC"] if "^GSPC" not in tickers else []))
    if not dati:
        sys.exit("Nessun dato scaricato (Yahoo non risponde): riprovo al prossimo giro.")
    # tensione sui mercati (guerre, crisi...): con il VIX sopra 30 ti avviso (solo avviso: vedi prova_filtri.py)
    vix = float(dati["^VIX"]["Close"].iloc[-1]) if "^VIX" in dati else None
    tensione = vix is not None and vix > E.VIX_SOGLIA
    if vix is not None:
        if tensione and not stato.get("tensione"):
            messaggi.append(f"🌩️ <b>Mercati in tensione</b>: l'indice della paura (VIX) è a {num(vix, 1)}, sopra {E.VIX_SOGLIA:.0f}. "
                            "Di solito succede con guerre, crisi o notizie forti. Il prezzo può muoversi più del solito: "
                            "le regole restano le stesse (nei test, dimezzare il rischio qui faceva guadagnare meno senza ridurre le discese).")
            annota(stato, ora, "Mercati", "Mercati in tensione", f"VIX a {num(vix, 1)}", "🌩️")
        elif not tensione and stato.get("tensione"):
            messaggi.append(f"🌤️ La tensione è scesa (VIX a {num(vix, 1)}).")
            annota(stato, ora, "Mercati", "Tensione finita", f"VIX a {num(vix, 1)}", "🌤️")
        stato["tensione"], stato["vix"] = tensione, round(vix, 1)
    eurusd = 1.08 if DEMO or "EURUSD=X" not in dati else float(dati["EURUSD=X"]["Close"].iloc[-1])

    # ---- 3. conto Capital.com (solo in modalità automatica) ----
    broker, conto, posizioni, risultati, blocco, attuale = None, None, [], None, None, None
    pos_trend: list[dict] = []
    if AUTOMATICO:
        broker = collega_broker()
        if broker is None:
            if stato.get("avviso_credenziali") != oggi:
                messaggi.append("🔑 La modalità automatica è scelta nel piano, ma mancano le chiavi di Capital.com "
                                "nei Secrets di GitHub. Per ora ti mando solo gli avvisi.")
                stato["avviso_credenziali"] = oggi
        else:
            try:
                broker.accedi()
                conto = broker.conto()
                posizioni = broker.posizioni()
                # le posizioni del trend mensile hanno la loro gestione: il resto del bot non le tocca
                # (riconoscibili anche dal fatto che NON hanno take profit: la Palestra lo mette sempre)
                deal_trend = stato.get("trend", {}).get("deal", {})
                del_trend = lambda p: p["dealId"] in deal_trend or (TREND.get("attivo") and p.get("tp") is None and p.get("stop") is None)
                pos_trend = [p for p in posizioni if del_trend(p)]
                posizioni = [p for p in posizioni if not del_trend(p)]
                risultati = aggiorna_periodi(stato, conto["saldo"] + conto["pl_aperto"], ora)
                blocco = limite_superato(risultati)
                attuale = progresso(stato, conto["saldo"])
            except C.CapitalErrore as e:
                broker = None
                print(f"Capital.com non raggiungibile: {e}")
                if stato.get("avviso_collegamento") != oggi:     # al massimo un avviso al giorno
                    messaggi.append(f"⚠️ Non riesco a collegarmi a Capital.com ({str(e)[:120]}). "
                                    "Finché non si risolve ti mando solo gli avvisi; riprovo ogni 30 minuti.")
                    stato["avviso_collegamento"] = oggi
    auto_attivo = broker is not None and not stato.get("pausa")

    # operazioni chiuse dall'ultimo giro (stop o take profit)
    if broker is not None:
        aperte_ora = {p["dealId"] for p in posizioni} | {p["dealId"] for p in pos_trend}   # il trend non è "chiuso"
        prima_aperte = stato.get("aperte", {})
        for deal, info in prima_aperte.items():
            if deal not in aperte_ora:
                euro_ris = risultato_chiusura(broker, info.get("epic", ""), info.get("aperta", "")) if info.get("epic") else None
                stato.setdefault("chiuse", []).append({"nome": info.get("nome", "Operazione"), "epic": info.get("epic"),
                                                       "palestra": bool(info.get("palestra")),
                                                       "aperta": info.get("aperta"), "chiusa": ora.isoformat(timespec="minutes"),
                                                       "euro": euro_ris})
                if euro_ris is None:
                    esito = "chiusa (stop-loss o take profit)"
                elif euro_ris > 0:
                    esito = f"chiusa in <b>guadagno: {euro(euro_ris)}</b> ✅ (take profit)"
                else:
                    esito = f"chiusa in <b>perdita: {euro(euro_ris)}</b> ❌ (stop-loss): fa parte del gioco, era già messa in conto"
                messaggi.append(f"🏁 <b>{info.get('nome', 'Operazione')}</b> {esito}\n{barra(attuale) if attuale is not None else ''}")
                annota(stato, ora, info.get("nome", "Operazione"), "Operazione chiusa",
                       "risultato non disponibile" if euro_ris is None else f"risultato {euro(euro_ris)}",
                       "🏁" if euro_ris is None else ("✅" if euro_ris > 0 else "❌"))
        stato["aperte"] = {p["dealId"]: {**{"nome": p["nome"], "epic": p["epic"], "aperta": ora.isoformat(timespec="minutes")},
                                         **prima_aperte.get(p["dealId"], {}), "epic": p["epic"]} for p in posizioni}
        # tempo scaduto (come nei test): dopo 60 giorni di borsa (~84 di calendario) senza stop né take profit, si chiude
        for p in list(posizioni):
            info = stato["aperte"].get(p["dealId"], {})
            try:
                giorni = (ora - datetime.fromisoformat(info["aperta"])).days
            except Exception:
                continue
            if giorni < GIORNI_MAX or not auto_attivo:
                continue
            try:
                broker.chiudi(p["dealId"])
            except C.CapitalErrore as e:
                print(f"Chiusura per tempo scaduto non riuscita su {p.get('nome')}: {e}")
                continue
            upl = float(p.get("upl") or 0)
            posizioni.remove(p)
            stato["aperte"].pop(p["dealId"], None)
            stato.setdefault("chiuse", []).append({"nome": info.get("nome", p.get("nome")), "epic": p.get("epic"),
                                                   "palestra": bool(info.get("palestra")), "aperta": info.get("aperta"),
                                                   "chiusa": ora.isoformat(timespec="minutes"), "euro": upl})
            messaggi.append(f"⏳ <b>{info.get('nome', p.get('nome'))}</b>: aperta da {giorni} giorni senza toccare né stop né "
                            f"take profit. Come da regola la chiudo: risultato circa <b>{euro(upl)}</b>.")
            annota(stato, ora, info.get("nome", p.get("nome")), "Chiusa per tempo scaduto", f"dopo {giorni} giorni, circa {euro(upl)}", "⏳")
        if blocco and stato.get("blocco_avvisato") != f"{blocco[0]}:{chiavi_periodo(ora)[blocco[0]]}":
            messaggi.append(f"⛔ <b>Mi fermo</b>: {blocco[1]}. Niente nuove operazioni "
                            f"{next(f for n, _, _, f in LIMITI if n == blocco[0])}. Fa parte del piano: proteggere il conto.")
            stato["blocco_avvisato"] = f"{blocco[0]}:{chiavi_periodo(ora)[blocco[0]]}"
            annota(stato, ora, "Conto", "Mi fermo", blocco[1], "⛔")

    if attuale is not None and OBIETTIVO > CAPITALE:
        tappe = stato["obiettivo_traccia"].setdefault("tappe", [])
        # tappe ogni 5% del percorso (con 100.000 → 200.000: ogni 5.000 €), al massimo UN messaggio per giro
        passo = max(100, round((OBIETTIVO - CAPITALE) / 20, -2))
        nuove = [t for t in range(int(CAPITALE + passo), int(OBIETTIVO) + 1, int(passo)) if attuale >= t and t not in tappe]
        if nuove:
            tappe.extend(nuove)
            t = max(nuove)
            fine = " 🏆 <b>Obiettivo raggiunto!</b> Ora rivediamo insieme il piano." if t >= OBIETTIVO else ""
            messaggi.append(f"🎉 Tappa superata: il tuo capitale del piano ha raggiunto <b>{num(t, 0)} €</b>.\n{barra(attuale)}{fine}")

    if broker is not None and auto_attivo and CFG and CFG.get("pareggio"):
        gestisci_pareggio(broker, stato, posizioni, messaggi)

    if "/stato" in comandi:
        messaggi.append(msg_stato(auto_attivo, conto, risultati, posizioni, attuale))
    if "/resoconto" in comandi:
        messaggi.append(msg_resoconto(stato, "📒 <b>Resoconto della settimana in corso</b>",
                                      risultati["settimana"] if risultati else None, 7, posizioni, attuale))
    chiave_sett = chiavi_periodo(ora)["settimana"]
    stato.setdefault("giri", {})[chiave_sett] = stato.get("giri", {}).get(chiave_sett, 0) + 1
    stato["giri"] = {k: v for k, v in stato["giri"].items() if k >= chiavi_periodo(ora - timedelta(days=21))["settimana"]}
    if ora.weekday() == 0 and ora.hour >= ORA_RIEPILOGO and stato.get("resoconto") != chiave_sett and not primo_giro:
        prec = stato.get("periodi", {}).get("settimana_prec", {})
        messaggi.append(msg_resoconto(stato, f"📒 <b>Resoconto settimanale</b> (settimana {prec.get('chiave', 'scorsa')})",
                                      prec.get("risultato"), 7, posizioni, attuale))
        stato["resoconto"] = chiave_sett

    # ---- 4. semafori: avvisi ed eventuali operazioni ----
    righe = []
    esclusi = set(PIANO.get("mercati_esclusi", []))
    for nome, (ticker, valuta) in L.mercati(PIANO).items():
        if ticker not in dati or nome in esclusi or ticker in esclusi:
            continue
        v = L.valuta(L.aggiungi_indicatori(dati[ticker]))
        righe.append({"nome": nome, "colore": v["colore"], "rsi": v["rsi"]})
        prima = stato["asset"].get(ticker, {})
        cambio = 1.0 if valuta == "EUR" else eurusd

        if not in_orario and not primo_giro:
            continue    # fuori dagli orari del piano: niente avvisi né operazioni, se ne riparla al mattino

        # Segnale della strategia promossa dalla ricerca (per il ritracciamento coincide con il semaforo verde)
        if CFG and CFG["strategia"] == "ritracciamento":
            segnale = v["colore"] == "VERDE" and prima.get("colore") != "VERDE" and prima.get("avvisato") != oggi
        elif CFG:
            df_s = BT.segnali_mercato(dati[ticker])
            idx = R.segnali(df_s, CFG["strategia"])
            giorno = str(df_s.index[-1].date())
            segnale = len(idx) > 0 and idx[-1] == len(df_s) - 1 and prima.get("segnale_giorno") != giorno
            if segnale:
                prima["segnale_giorno"] = giorno
        else:
            segnale = False
            if not primo_giro and v["colore"] == "VERDE" and prima.get("colore") != "VERDE" and prima.get("avvisato") != oggi:
                messaggi.append(f"🔬 <b>{nome}</b>: semaforo verde, ma <b>non opero</b>. La ricerca di questa settimana dice che "
                                "con i costi reali nessuna regola ha un vantaggio affidabile. Lo considero solo come studio.")
                annota(stato, ora, nome, "Semaforo verde, non opero",
                       "la ricerca non trova un vantaggio affidabile con i costi reali", "🔬")
                prima["avvisato"] = oggi

        if not primo_giro and segnale:
            rischio = L.rischio_per(ticker, PIANO, RISCHIO)
            p = L.piano(CAPITALE * cambio, rischio, v["close"], v["atr"])
            motivo = ""
            consentito, perche_no = permesso_cfg(dati, stato, oggi)
            evento = E.evento_vicino(ticker, ora.date(), stato.setdefault("eventi", {}))
            if not consentito:
                motivo = f"oggi la ricerca dice di non operare ({perche_no})"
            elif evento:
                motivo = evento
            elif auto_attivo and blocco:
                motivo = blocco[1]
            elif auto_attivo:
                try:
                    op, motivo = prova_ad_aprire(broker, ticker, nome, v, eurusd, posizioni)
                except C.CapitalErrore as e:
                    op, motivo = None, f"Capital.com ha rifiutato l'ordine ({str(e)[:100]})"
                if op:
                    posizioni.append({"epic": op["epic"], "nome": nome, "dealId": op["dealId"]})
                    stato.setdefault("aperte", {})[op["dealId"]] = {"nome": nome, "epic": op["epic"],
                                                                    "aperta": ora.isoformat(timespec="minutes"),
                                                                    "livello": op["livello"], "distanza": op["distanza"],
                                                                    "palestra": bool(CFG and CFG.get("palestra"))}
                    stato.setdefault("registro", []).append({k: op[k] for k in ("nome", "size", "livello", "stop", "tp")}
                                                            | {"data": ora.isoformat(timespec="minutes")})
                    messaggi.append(msg_aperta(nome, {"valuta": op["valuta"]}, op, v, op["rischio_eur"], len(posizioni)))
                    annota(stato, ora, nome, "Operazione aperta" + (" (palestra)" if CFG.get("palestra") else ""),
                           f"{quote(op['size'])} contratti a {prezzo(op['livello'])}, stop {prezzo(op['stop'])}, "
                           f"take profit {prezzo(op['tp'])}", "✅")
            elif AUTOMATICO and stato.get("pausa"):
                motivo = "sono in pausa (scrivi /riprendi per farmi ripartire)"
            if not (auto_attivo and not motivo):
                messaggi.append(msg_verde(nome, ticker, valuta, v, p, cambio, rischio, motivo))
                if motivo:
                    annota(stato, ora, nome, "Segnale, non apro", motivo, "⏸️")
            prima["avvisato"] = oggi
        elif not primo_giro and CFG and CFG["strategia"] == "ritracciamento" and prima.get("colore") == "VERDE" \
                and v["colore"] != "VERDE":
            messaggi.append(msg_non_piu_verde(nome, v["colore"], auto_attivo))
        prima["colore"] = v["colore"]
        stato["asset"][ticker] = prima

    # ---- 4b. trend mensile (portafoglio lento, una volta al mese) ----
    if PIANO.get("prova_stop_garantito") and "stop_garantito" not in stato:
        stato["stop_garantito"] = {}                    # la prossima operazione del trend lo prova
    if broker is not None and auto_attivo and TREND.get("attivo"):
        nomi_t = {t: n for n, (t, _) in L.mercati(PIANO).items() if t in dati}
        try:
            TM.gestisci(broker, stato, dati, nomi_t, pos_trend, eurusd, ora, float(TREND.get("capitale", 50000)), messaggi, annota)
            deal_trend = stato["trend"]["deal"]
            pos_trend = [p for p in broker.posizioni() if p["dealId"] in deal_trend or (p.get("tp") is None and p.get("stop") is None)]
        except C.CapitalErrore as e:
            print(f"Trend mensile non gestito in questo giro: {e}")

    # ---- 5. benvenuto e riepilogo del mattino ----
    if args.prova and broker is not None:
        messaggi.insert(0, msg_stato(auto_attivo, conto, risultati, posizioni, attuale))
    if args.prova or primo_giro:
        modo = ("Opero da solo sul conto <b>Demo</b> di Capital.com seguendo il tuo piano e la mia ricerca settimanale, "
                "e ti avviso di ogni operazione.\n" + descrizione_ricerca()
                if AUTOMATICO else "Non invio mai ordini: decidi sempre tu.")
        messaggi.insert(0, msg_riepilogo(
            righe, "👋 <b>Ciao! Sono il tuo Tutor di Trading.</b>\n"
                   f"Controllo i mercati ogni 30 minuti, giorno e notte, e ti scrivo quando un semaforo diventa verde. {modo}\n"
                   "Comandi: /stato · /resoconto · /stop · /riprendi\n\n<b>La situazione adesso:</b>"))
    elif ora.hour >= ORA_RIEPILOGO and stato.get("riepilogo") != oggi:
        titolo = f"☀️ <b>Buongiorno! Il semaforo di oggi</b> ({ora:%d/%m})"
        if attuale is not None and OBIETTIVO:
            titolo += "\n" + barra(attuale)
        messaggi.insert(0, msg_riepilogo(righe, titolo))
    if ora.hour >= ORA_RIEPILOGO:
        stato["riepilogo"] = oggi

    for m in messaggi:
        invia(m, args.a_secco, silenzioso=not in_orario)
    stato["ultimo_giro"] = ora.isoformat(timespec="minutes")
    stato["registro"] = stato.get("registro", [])[-200:]
    # Per il diario nell'app: capitale del piano nel tempo e posizioni del momento
    if attuale is not None:
        stato.setdefault("storia", []).append([ora.isoformat(timespec="minutes"), round(attuale, 2)])
        stato["storia"] = stato["storia"][-3000:]
    if broker is not None:
        stato["posizioni"] = [{k: p.get(k) for k in ("nome", "epic", "size", "livello", "stop", "tp", "upl", "bid")}
                              for p in posizioni if "size" in p]
        stato["posizioni_trend"] = [{k: p.get(k) for k in ("nome", "epic", "size", "livello", "stop", "tp", "upl", "bid")}
                                    for p in pos_trend]
        stato.setdefault("trend", {})["capitale"] = float(TREND.get("capitale", 0) or 0)
    stato["modalita"] = "automatica" if auto_attivo else ("pausa" if stato.get("pausa") else "avvisi")
    stato["capitale_piano"], stato["obiettivo"] = CAPITALE, OBIETTIVO
    STATO_FILE.write_text(json.dumps(stato, indent=1, ensure_ascii=False))
    print(f"Giro completato: {len(righe)} mercati controllati, {len(messaggi)} messaggi, "
          f"automatico {'attivo' if auto_attivo else 'spento'}.")


if __name__ == "__main__":
    main()
