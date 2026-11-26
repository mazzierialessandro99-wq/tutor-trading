"""
TREND MENSILE — la strategia promossa dalla ricerca_trend.py (versione senza leva), eseguita sul conto DEMO.

Una volta al mese (al primo giro del mese nuovo):
  • per ogni mercato si guarda il rendimento degli ultimi 6 mesi: se è positivo il mercato si tiene, altrimenti no
  • quanto: meno sui mercati agitati, di più su quelli calmi (40% di volatilità obiettivo diviso per il numero di
    mercati), al massimo il 100% del capitale dedicato (niente leva)
  • si esce dai mercati che non sono più in trend, si entra in quelli nuovi; gli altri si lasciano come sono
Niente stop loss né take profit: in questa strategia la protezione è l'uscita a fine mese se il trend si gira.
È un ESPERIMENTO sul Demo: con i CFD le commissioni notturne pesano (circa 9% l'anno), per questo nel resoconto le
mostro a parte, così vediamo come sarebbe andata con ETF/azioni vere.
"""
from __future__ import annotations

import numpy as np

import capital as C

MESI = 6
VOL_OBIETTIVO = 0.40
MAX_TENTATIVI = 6


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
    for d in [d for d in deal if d not in vivi]:          # chiuse da fuori (a mano o dal broker)
        deal.pop(d)
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
                if not m or m["valuta"] not in ("EUR", "USD"):
                    tr["cambi"].append(["saltato", t, w])
                    continue
                if not m["aperto"]:
                    rimasti.append(t)                       # mercato chiuso: riprovo al prossimo giro
                    continue
                cambio = 1.0 if m["valuta"] == "EUR" else eurusd
                size = min(C.arrotonda_size(w * capitale * cambio / m["offer"], m["passo"]), m["max_size"])
                if size < m["min_size"]:
                    tr["cambi"].append(["troppo piccolo", t, w])
                    continue
                esito = broker.compra(m["epic"], size)
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
