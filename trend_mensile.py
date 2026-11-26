"""
TREND MENSILE — la strategia promossa dalla ricerca_trend.py (versione senza leva), eseguita sul conto DEMO.

Una volta al mese (al primo giro del mese nuovo):
  • per ogni mercato si guarda il rendimento degli ultimi 6 mesi: se è positivo il mercato si tiene, altrimenti no
  • quanto: meno sui mercati agitati, di più su quelli calmi (40% di volatilità obiettivo diviso per il numero di
    mercati), al massimo il 100% del capitale dedicato (niente leva)
  • si esce dai mercati che non sono più in trend, si entra in quelli nuovi; gli altri si lasciano come sono
Stop loss SEMPRE (regola del piano): un "paracadute" largo, a 2 volte l'oscillazione tipica di un mese sotto il prezzo
d'ingresso (es. un mercato che si muove del 20% l'anno → stop circa 11,5% sotto). Se scatta, quel mercato resta fuori
fino al mese dopo. Take profit SEMPRE: al doppio della distanza dello stop (come la Palestra); se scatta si incassa e,
se il trend c'è ancora, si rientra al ribilanciamento del mese dopo. Senza nessuno dei due, si esce a fine mese se il
trend si gira. (Stop e take profit fissi NON erano nella ricerca: li misuriamo dal vivo.)
È un ESPERIMENTO sul Demo: con i CFD le commissioni notturne pesano (circa 9% l'anno), per questo nel resoconto le
mostro a parte, così vediamo come sarebbe andata con ETF/azioni vere.
"""
from __future__ import annotations

import numpy as np

import capital as C

MESI = 6
VOL_OBIETTIVO = 0.40
MAX_TENTATIVI = 6
STOP_SIGMA_MESE = 2.0
RR = 2.0


def quota_stop(dati: dict, t: str) -> float:
    """Distanza dello stop in % del prezzo: 2 volte l'oscillazione mensile (volatilità annua / radice di 12)."""
    d = dati.get(t)
    v = float(d["Close"].pct_change().iloc[-63:].std() * np.sqrt(252)) if d is not None and len(d) > 70 else 0.3
    return min(max(STOP_SIGMA_MESE * v / np.sqrt(12), 0.05), 0.5)


def livelli(prezzo: float, quota: float, min_distanza: float = 0.0) -> tuple[float, float]:
    """(stop, take profit) per un acquisto a questo prezzo."""
    distanza = max(prezzo * quota, min_distanza or 0.0)
    dec = 5 if prezzo < 10 else 2
    return round(prezzo - distanza, dec), round(prezzo + RR * distanza, dec)


def pesi_obiettivo(dati: dict, tickers: list[str]) -> dict[str, float]:
    """Peso (quota del capitale dedicato) per ogni mercato da tenere questo mese."""
    mom, vol = {}, {}
    for t in tickers:
        d = dati.get(t)
        if d is None or len(d) < 21 * MESI + 5:
            continue
        c = d["Close"]
        v = float(c.pct_change().iloc[-63:].std() * np.sqrt(252))
        if not v > 0:
            continue
        mom[t], vol[t] = float(c.iloc[-1] / c.iloc[-1 - 21 * MESI] - 1), v
    if not mom:
        return {}
    n = len(mom)
    pesi = {t: VOL_OBIETTIVO / vol[t] / n for t in mom if mom[t] > 0}
    lordo = sum(pesi.values())
    if lordo > 1:
        pesi = {t: w / lordo for t, w in pesi.items()}
    return {t: round(w, 4) for t, w in pesi.items()}


def gestisci(broker, stato: dict, dati: dict, nomi: dict, pos_trend: list[dict], eurusd: float, ora, capitale: float,
             messaggi: list[str], annota) -> None:
    tr = stato.setdefault("trend", {})
    deal = tr.setdefault("deal", {})                       # dealId -> ticker
    epic_di = tr.setdefault("epic", {})                   # epic Capital.com -> ticker
    vivi = {p["dealId"] for p in pos_trend}
    for d in [d for d in deal if d not in vivi]:          # chiuse da stop, take profit (o a mano)
        t = deal.pop(d)
        messaggi.append(f"🏁 <b>Trend mensile · {nomi.get(t, t)}</b>: posizione chiusa da stop loss o take profit. "
                        "Se il trend c'è ancora, rientro al ribilanciamento del mese prossimo.")
        annota(stato, ora, f"Trend · {nomi.get(t, t)}", "Chiusa da stop o take profit", "rientro eventuale a inizio mese", "🏁")
    for p in pos_trend:                                    # posizioni del trend non ancora collegate al loro mercato
        if p["dealId"] not in deal:
            t = epic_di.get(p["epic"]) or next((t for t in nomi if C.EPIC.get(t, t) == p["epic"]
                                                or t.split(".")[0].replace("-USD", "USD") == p["epic"]), None)
            if not t:                                       # ultima prova: chiedo a Capital.com l'epic dei mercati comprati
                for a, tk, _ in tr.get("cambi", []):
                    if a == "entra" and tk not in epic_di.values():
                        try:
                            m = broker.trova(tk, nomi.get(tk, tk))
                        except C.CapitalErrore:
                            m = None
                        if m:
                            epic_di[m["epic"]] = tk
                            if m["epic"] == p["epic"]:
                                t = tk
                                break
            if t:
                deal[p["dealId"]] = t
            else:
                print(f"Trend mensile: posizione {p['epic']} senza mercato riconosciuto")
    mese = f"{ora:%Y-%m}"
    if tr.get("mese") != mese:
        tr.update(mese=mese, obiettivo=pesi_obiettivo(dati, list(nomi)), tentativi={}, cambi=[], annunciato=False)
        tr["da_fare"] = sorted(set(tr["obiettivo"]) | set(deal.values()))
    # stop loss e take profit sempre: le posizioni del trend che non li hanno li ricevono subito
    for p in pos_trend:
        t = deal.get(p["dealId"])
        if t and (p.get("stop") is None or p.get("tp") is None) and p.get("bid"):
            livello, bid = float(p["livello"]), float(p["bid"])
            stop, tp = livelli(livello, quota_stop(dati, t))
            stop, tp = min(stop, livelli(bid, quota_stop(dati, t))[0]), max(tp, bid * 1.01)   # sempre dal lato giusto del prezzo
            try:
                broker.sposta_stop(p["dealId"], p.get("stop") or stop, p.get("tp") or round(tp, 5 if bid < 10 else 2))
            except C.CapitalErrore as e:
                print(f"Trend mensile, stop/take profit non messi su {t}: {e}")
    rimasti = []
    for t in tr.get("da_fare", []):
        w = tr["obiettivo"].get(t, 0.0)
        miei = [d for d, tk in deal.items() if tk == t]
        try:
            if w <= 0 and miei:
                for d in miei:
                    broker.chiudi(d)
                    deal.pop(d)
                tr["cambi"].append(["esce", t, 0])
            elif w > 0 and not miei:
                m = broker.trova(t, nomi.get(t, t))
                if m:
                    tr.setdefault("attese", {}).pop(t, None)
                if not m or m["valuta"] not in ("EUR", "USD"):
                    tr["cambi"].append(["saltato", t, w])
                    continue
                if not m["aperto"]:
                    rimasti.append(t)                       # mercato chiuso: riprovo al prossimo giro
                    tr.setdefault("attese", {})[t] = f"{ora:%H:%M} {m['epic']} {m.get('stato')}"
                    continue
                cambio = 1.0 if m["valuta"] == "EUR" else eurusd
                size = min(C.arrotonda_size(w * capitale * cambio / m["offer"], m["passo"]), m["max_size"])
                if size < m["min_size"]:
                    tr["cambi"].append(["troppo piccolo", t, w])
                    continue
                stop, tp = livelli(m["offer"], quota_stop(dati, t), m["min_distanza_stop"])
                prova = stato.get("stop_garantito")
                if prova is not None and not prova.get("fatto"):
                    # PROVA dello stop garantito (una sola operazione): chiude esattamente allo stop anche nei salti di prezzo
                    try:
                        esito = broker.compra(m["epic"], size, stop=stop, tp=tp, garantito=True)
                        prova.update(fatto=True, accettato=True, ticker=t, nome=nomi.get(t, t), dealId=esito["dealId"],
                                     stop=stop, prezzo=m["offer"], size=size, data=f"{ora:%Y-%m-%d %H:%M}")
                        messaggi.append(f"🛡️ <b>Prova dello stop garantito</b>: comprato <b>{nomi.get(t, t)}</b> con stop garantito a "
                                        f"{stop}. Capital.com l'ha accettato. Se scatta, controllo quanto costa davvero.")
                    except C.CapitalErrore as e:
                        prova.update(tentativi=prova.get("tentativi", 0) + 1, ultimo_rifiuto=str(e)[:200])
                        print(f"Stop garantito rifiutato su {t}: {e}")
                        if prova["tentativi"] >= 3:
                            prova.update(fatto=True, accettato=False)
                            messaggi.append(f"🛡️ <b>Prova dello stop garantito</b>: Capital.com lo rifiuta ({str(e)[:150]}). "
                                            "Continuo con gli stop normali.")
                        esito = broker.compra(m["epic"], size, stop=stop, tp=tp)
                else:
                    esito = broker.compra(m["epic"], size, stop=stop, tp=tp)
                deal[esito["dealId"]] = t
                epic_di[m["epic"]] = t
                tr["cambi"].append(["entra", t, w])
        except C.CapitalErrore as e:
            n = tr["tentativi"][t] = tr["tentativi"].get(t, 0) + 1
            print(f"Trend mensile, {t}: {e}")
            if n < MAX_TENTATIVI:
                rimasti.append(t)
            else:
                tr["cambi"].append(["errore", t, w])
    tr["da_fare"] = rimasti
    if not rimasti and not tr.get("annunciato"):
        tr["annunciato"] = True
        entra = [nomi.get(t, t) for a, t, _ in tr["cambi"] if a == "entra"]
        esce = [nomi.get(t, t) for a, t, _ in tr["cambi"] if a == "esce"]
        tenuti = sorted(set(deal.values()), key=lambda t: -tr["obiettivo"].get(t, 0))
        investito = sum(tr["obiettivo"].get(t, 0) for t in tenuti) * 100
        testo = (f"📅 <b>Trend mensile · {ora:%m/%Y}</b>\nTengo <b>{len(tenuti)}</b> mercati in trend da 6 mesi "
                 f"(circa il {investito:.0f}% dei {capitale:,.0f} € dedicati).".replace(",", "."))
        if entra:
            testo += "\n➕ Entro: " + ", ".join(entra)
        if esce:
            testo += "\n➖ Esco: " + ", ".join(esce)
        if tenuti:
            testo += "\nPrincipali: " + ", ".join(f"{nomi.get(t, t)} {tr['obiettivo'].get(t, 0) * 100:.0f}%" for t in tenuti[:6])
        messaggi.append(testo)
        annota(stato, ora, "Trend mensile", f"Ribilanciamento di {ora:%m/%Y}",
               f"{len(tenuti)} mercati tenuti, {len(entra)} nuovi, {len(esce)} usciti", "📅")
