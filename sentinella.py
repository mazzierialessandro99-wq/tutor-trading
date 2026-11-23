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
Comandi su Telegram (letti a ogni giro): /stop  /riprendi  /stato

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

import capital as C
import logica as L

ROMA = ZoneInfo("Europe/Rome")
APP_URL = os.environ.get("APP_URL", "https://tutor-trading-ale.streamlit.app")
STATO_FILE = Path(os.environ.get("STATO_FILE", "stato_sentinella.json"))
PIANO = L.carica_piano()                                 # il tuo piano personale (piano.json)
CAPITALE = float(os.environ.get("CAPITALE") or PIANO.get("capitale", 1000))   # in euro
RISCHIO = float(os.environ.get("RISCHIO") or PIANO.get("rischio_per_operazione", 1))  # % per operazione
DALLE, ALLE = PIANO.get("orari_avvisi", ["00:00", "23:59"])
MAX_APERTE = int(PIANO.get("max_posizioni_aperte", 3))
AUTOMATICO = PIANO.get("modalita") == "automatico"
ORA_RIEPILOGO = int(os.environ.get("ORA_RIEPILOGO", "8"))
DEMO = os.environ.get("TUTOR_DEMO") == "1"               # dati inventati, solo per prove senza internet
BROKER_SIMULATO = os.environ.get("BROKER_SIMULATO") == "1"   # conto finto, solo per prove

EMOJI = {"VERDE": "🟢", "GIALLO": "🟡", "ROSSO": "🔴"}


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


def scarica_tutti(tickers: list[str], periodo: str = "2y") -> dict[str, pd.DataFrame]:
    """Candele giornaliere di tutti i mercati, in una sola richiesta."""
    if DEMO:
        return {t: _demo(t) for t in tickers}
    import yfinance as yf
    grezzi = yf.download(tickers, period=periodo, interval="1d", auto_adjust=True, progress=False,
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
        f"✅ <b>Ho aperto {nome}</b> sul conto Demo\n"
        f"Comprati <b>{quote(op['size'])}</b> contratti a <b>{prezzo(op['livello'], m['valuta'])}</b>\n"
        f"Stop-loss <b>{prezzo(op['stop'], m['valuta'])}</b> · Take profit <b>{prezzo(op['tp'], m['valuta'])}</b>\n"
        f"Rischio ≈ {num(rischio_eur)} € · obiettivo ≈ {num(rischio_eur * L.RR)} €\n\n"
        f"Perché: trend positivo e RSI a {v['rsi']:.0f} in risalita dopo una pausa.\n"
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
            per[nome] = {"chiave": chiave, "inizio": valore}
        risultati[nome] = valore - per[nome]["inizio"]
    return risultati


def limite_superato(risultati: dict) -> tuple[str, str, float] | None:
    for nome, campo, testo, fino in LIMITI:
        soglia = CAPITALE * float(PIANO.get(campo, 100)) / 100
        if risultati.get(nome, 0) <= -soglia:
            return nome, f"limite di perdita {testo} raggiunto ({euro(risultati[nome])}, soglia −{num(soglia)} €)", soglia
    return None


def msg_stato(auto_attivo: bool, conto: dict | None, risultati: dict | None, posizioni: list[dict]) -> str:
    righe = [f"📊 <b>Stato dell'assistente</b>",
             f"Modalità: {'🤖 automatica (Demo)' if auto_attivo else '✋ solo avvisi' if not AUTOMATICO else '⏸️ in pausa (/riprendi per ripartire)'}"]
    if conto:
        righe.append(f"Saldo demo: {num(conto['saldo'])} € · aperto: {euro(conto['pl_aperto'])}")
    if risultati:
        for nome, campo, testo, _ in LIMITI:
            righe.append(f"Risultato {testo}: {euro(risultati[nome])} (limite −{num(CAPITALE * float(PIANO.get(campo, 100)) / 100)} €)")
    if posizioni:
        righe.append(f"\nPosizioni aperte ({len(posizioni)}/{MAX_APERTE}):")
        righe += [f"• {p['nome']}: {quote(float(p['size']))} @ {prezzo(float(p['livello']))} · {euro(float(p.get('upl') or 0))}"
                  for p in posizioni]
    elif conto:
        righe.append("\nNessuna posizione aperta.")
    righe.append(f"\nComandi: /stop · /riprendi · /stato\n👉 {APP_URL}")
    return "\n".join(righe)


# ------------------------------------------------------------------------------
# ESECUZIONE AUTOMATICA (solo DEMO)
# ------------------------------------------------------------------------------
def prova_ad_aprire(broker, ticker: str, nome: str, v: dict, eurusd: float, posizioni: list[dict]) -> tuple[dict | None, str]:
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
    rischio_pct = L.rischio_per(ticker, PIANO, RISCHIO)
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
          "valuta": m["valuta"]}
    return op, ""


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
    tickers = [t for t, _ in L.ASSET.values()]
    dati = scarica_tutti(tickers + ["EURUSD=X"])
    if not dati:
        sys.exit("Nessun dato scaricato (Yahoo non risponde): riprovo al prossimo giro.")
    eurusd = 1.08 if DEMO or "EURUSD=X" not in dati else float(dati["EURUSD=X"]["Close"].iloc[-1])

    # ---- 3. conto Capital.com (solo in modalità automatica) ----
    broker, conto, posizioni, risultati, blocco = None, None, [], None, None
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
                risultati = aggiorna_periodi(stato, conto["saldo"] + conto["pl_aperto"], ora)
                blocco = limite_superato(risultati)
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
        aperte_ora = {p["dealId"] for p in posizioni}
        prima_aperte = stato.get("aperte", {})
        for deal, info in prima_aperte.items():
            if deal not in aperte_ora:
                saldo_txt = f" Saldo demo: {num(conto['saldo'])} €." if conto else ""
                messaggi.append(f"🏁 <b>{info.get('nome', 'Operazione')}</b> chiusa (stop-loss o take profit).{saldo_txt}\n"
                                "Annota nel diario com'è andata e cosa hai imparato.")
        stato["aperte"] = {p["dealId"]: prima_aperte.get(p["dealId"], {"nome": p["nome"]}) for p in posizioni}
        if blocco and stato.get("blocco_avvisato") != f"{blocco[0]}:{chiavi_periodo(ora)[blocco[0]]}":
            messaggi.append(f"⛔ <b>Mi fermo</b>: {blocco[1]}. Niente nuove operazioni "
                            f"{next(f for n, _, _, f in LIMITI if n == blocco[0])}. Fa parte del piano: proteggere il conto.")
            stato["blocco_avvisato"] = f"{blocco[0]}:{chiavi_periodo(ora)[blocco[0]]}"

    if "/stato" in comandi:
        messaggi.append(msg_stato(auto_attivo, conto, risultati, posizioni))

    # ---- 4. semafori: avvisi ed eventuali operazioni ----
    righe = []
    esclusi = set(PIANO.get("mercati_esclusi", []))
    for nome, (ticker, valuta) in L.ASSET.items():
        if ticker not in dati or nome in esclusi or ticker in esclusi:
            continue
        v = L.valuta(L.aggiungi_indicatori(dati[ticker]))
        righe.append({"nome": nome, "colore": v["colore"], "rsi": v["rsi"]})
        prima = stato["asset"].get(ticker, {})
        cambio = 1.0 if valuta == "EUR" else eurusd

        if not in_orario and not primo_giro:
            continue    # fuori dagli orari del piano: niente avvisi né operazioni, se ne riparla al mattino
        if not primo_giro and v["colore"] == "VERDE" and prima.get("colore") != "VERDE" \
                and prima.get("avvisato") != oggi:
            rischio = L.rischio_per(ticker, PIANO, RISCHIO)
            p = L.piano(CAPITALE * cambio, rischio, v["close"], v["atr"])
            motivo = ""
            if auto_attivo and blocco:
                motivo = blocco[1]
            elif auto_attivo:
                try:
                    op, motivo = prova_ad_aprire(broker, ticker, nome, v, eurusd, posizioni)
                except C.CapitalErrore as e:
                    op, motivo = None, f"Capital.com ha rifiutato l'ordine ({str(e)[:100]})"
                if op:
                    posizioni.append({"epic": op["epic"], "nome": nome, "dealId": op["dealId"]})
                    stato.setdefault("aperte", {})[op["dealId"]] = {"nome": nome, "aperta": ora.isoformat(timespec="minutes")}
                    stato.setdefault("registro", []).append({k: op[k] for k in ("nome", "size", "livello", "stop", "tp")}
                                                            | {"data": ora.isoformat(timespec="minutes")})
                    messaggi.append(msg_aperta(nome, {"valuta": op["valuta"]}, op, v, op["rischio_eur"], len(posizioni)))
            elif AUTOMATICO and stato.get("pausa"):
                motivo = "sono in pausa (scrivi /riprendi per farmi ripartire)"
            if not (auto_attivo and not motivo):
                messaggi.append(msg_verde(nome, ticker, valuta, v, p, cambio, rischio, motivo))
            prima["avvisato"] = oggi
        elif not primo_giro and prima.get("colore") == "VERDE" and v["colore"] != "VERDE":
            messaggi.append(msg_non_piu_verde(nome, v["colore"], auto_attivo))
        prima["colore"] = v["colore"]
        stato["asset"][ticker] = prima

    # ---- 5. benvenuto e riepilogo del mattino ----
    if args.prova or primo_giro:
        modo = ("Opero da solo sul conto <b>Demo</b> di Capital.com seguendo il tuo piano, e ti avviso di ogni operazione."
                if AUTOMATICO else "Non invio mai ordini: decidi sempre tu.")
        messaggi.insert(0, msg_riepilogo(
            righe, "👋 <b>Ciao! Sono il tuo Tutor di Trading.</b>\n"
                   f"Controllo i mercati ogni 30 minuti, giorno e notte, e ti scrivo quando un semaforo diventa verde. {modo}\n"
                   "Comandi: /stato · /stop · /riprendi\n\n<b>La situazione adesso:</b>"))
    elif ora.hour >= ORA_RIEPILOGO and stato.get("riepilogo") != oggi:
        messaggi.insert(0, msg_riepilogo(righe, f"☀️ <b>Buongiorno! Il semaforo di oggi</b> ({ora:%d/%m})"))
    if ora.hour >= ORA_RIEPILOGO:
        stato["riepilogo"] = oggi

    for m in messaggi:
        invia(m, args.a_secco, silenzioso=not in_orario)
    stato["ultimo_giro"] = ora.isoformat(timespec="minutes")
    stato["registro"] = stato.get("registro", [])[-200:]
    STATO_FILE.write_text(json.dumps(stato, indent=1, ensure_ascii=False))
    print(f"Giro completato: {len(righe)} mercati controllati, {len(messaggi)} messaggi, "
          f"automatico {'attivo' if auto_attivo else 'spento'}.")


if __name__ == "__main__":
    main()
