"""
COLLEGAMENTO A CAPITAL.COM — SOLO CONTO DEMO.

Usato dalla sentinella in modalità automatica per:
  • leggere saldo e posizioni aperte
  • trovare lo strumento giusto (epic) e le sue regole (quantità minima)
  • aprire una posizione di ACQUISTO sempre con Stop-loss e Take profit

SICUREZZA: l'indirizzo del server è quello del DEMO ed è scritto qui sotto, non si può cambiare
da fuori. Per usare un conto reale bisognerebbe modificare questo file di proposito.

Credenziali (mai nel codice, vanno nei Secrets di GitHub):
    CAPITAL_API_KEY      la chiave API creata nelle impostazioni di Capital.com
    CAPITAL_IDENTIFIER   l'email del tuo account Capital.com
    CAPITAL_PASSWORD     la password personalizzata scelta quando hai creato la chiave API
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request

DEMO_URL = "https://demo-api-capital.backend-capital.com/api/v1"   # SOLO DEMO, di proposito fisso

# Nome dello strumento su Capital.com (epic) per ogni mercato sorvegliato. Se uno non esiste, si cerca per nome.
EPIC = {
    "^GSPC": "US500", "^NDX": "US100", "^DJI": "US30", "^GDAXI": "DE40", "FTSEMIB.MI": "IT40",
    "^STOXX50E": "EU50", "GC=F": "GOLD", "SI=F": "SILVER", "CL=F": "OIL_CRUDE",
    "EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "BTC-USD": "BTCUSD", "ETH-USD": "ETHUSD",
    "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA", "AMZN": "AMZN", "GOOGL": "GOOGL",
    "META": "META", "TSLA": "TSLA",
}


class CapitalErrore(Exception):
    pass


def credenziali_presenti() -> bool:
    return all(os.environ.get(k) for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))


class CapitalDemo:
    def __init__(self):
        self.cst = self.token = None

    # ---- chiamate di base ----
    def _chiama(self, metodo: str, percorso: str, corpo: dict | None = None, auth: bool = True):
        intest = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            intest.update({"CST": self.cst, "X-SECURITY-TOKEN": self.token})
        else:
            intest["X-CAP-API-KEY"] = os.environ["CAPITAL_API_KEY"]
        dati = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(DEMO_URL + percorso, data=dati, method=metodo, headers=intest)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                testo = r.read().decode() or "{}"
                return json.loads(testo), r.headers
        except urllib.error.HTTPError as e:
            dettaglio = e.read().decode(errors="ignore")[:200]
            raise CapitalErrore(f"{metodo} {percorso} -> {e.code} {dettaglio}") from None

    def accedi(self):
        _, h = self._chiama("POST", "/session", {
            "identifier": os.environ["CAPITAL_IDENTIFIER"],
            "password": os.environ["CAPITAL_PASSWORD"],
            "encryptedPassword": False,
        }, auth=False)
        self.cst, self.token = h.get("CST"), h.get("X-SECURITY-TOKEN")
        if not self.cst or not self.token:
            raise CapitalErrore("Accesso non riuscito: controlla chiave API, email e password della chiave.")

    # ---- conto e posizioni ----
    def conto(self) -> dict:
        dati, _ = self._chiama("GET", "/accounts")
        conti = dati.get("accounts", [])
        if not conti:
            raise CapitalErrore("Nessun conto trovato.")
        c = next((x for x in conti if x.get("preferred")), conti[0])
        b = c.get("balance", {})
        return {"valuta": c.get("currency", "EUR"), "saldo": float(b.get("balance", 0)),
                "pl_aperto": float(b.get("profitLoss", 0)), "disponibile": float(b.get("available", 0))}

    def posizioni(self) -> list[dict]:
        dati, _ = self._chiama("GET", "/positions")
        uscita = []
        for p in dati.get("positions", []):
            pos, mkt = p.get("position", {}), p.get("market", {})
            uscita.append({"epic": mkt.get("epic"), "nome": mkt.get("instrumentName"), "dealId": pos.get("dealId"),
                           "size": pos.get("size"), "direzione": pos.get("direction"), "livello": pos.get("level"),
                           "stop": pos.get("stopLevel"), "tp": pos.get("profitLevel"), "upl": pos.get("upl"),
                           "bid": mkt.get("bid")})
        return uscita

    # ---- strumenti ----
    def mercato(self, epic: str) -> dict | None:
        try:
            dati, _ = self._chiama("GET", f"/markets/{epic}")
        except CapitalErrore:
            return None
        ins, reg, snap = dati.get("instrument", {}), dati.get("dealingRules", {}), dati.get("snapshot", {})
        val = lambda k: float((reg.get(k) or {}).get("value") or 0)
        return {"epic": ins.get("epic", epic), "nome": ins.get("name", epic), "valuta": ins.get("currency", "USD"),
                "min_size": val("minDealSize") or 0.01, "passo": val("minSizeIncrement") or val("minDealSize") or 0.01,
                "max_size": val("maxDealSize") or 1e9, "min_distanza_stop": val("minStopOrProfitDistance"),
                "aperto": snap.get("marketStatus") == "TRADEABLE",
                "bid": float(snap.get("bid") or 0), "offer": float(snap.get("offer") or 0)}

    def trova(self, ticker: str, nome: str) -> dict | None:
        m = self.mercato(EPIC.get(ticker, ticker))
        if m:
            return m
        dati, _ = self._chiama("GET", "/markets?searchTerm=" + urllib.request.quote(nome.split(" (")[0]))
        for x in dati.get("markets", [])[:3]:
            m = self.mercato(x.get("epic"))
            if m:
                return m
        return None

    # ---- ordini ----
    def sposta_stop(self, deal_id: str, stop: float, tp: float | None = None):
        corpo = {"stopLevel": stop, "guaranteedStop": False}
        if tp:
            corpo["profitLevel"] = tp
        dati, _ = self._chiama("PUT", f"/positions/{deal_id}", corpo)
        ref = dati.get("dealReference")
        if ref:
            conf, _ = self._chiama("GET", f"/confirms/{ref}")
            if conf.get("dealStatus") not in (None, "ACCEPTED"):
                raise CapitalErrore(f"Modifica rifiutata: {conf.get('reason') or conf.get('dealStatus')}")

    def compra(self, epic: str, size: float, stop: float, tp: float) -> dict:
        corpo = {"epic": epic, "direction": "BUY", "size": size, "guaranteedStop": False,
                 "stopLevel": stop, "profitLevel": tp}
        dati, _ = self._chiama("POST", "/positions", corpo)
        ref = dati.get("dealReference")
        if not ref:
            raise CapitalErrore(f"Ordine non accettato: {dati}")
        conf, _ = self._chiama("GET", f"/confirms/{ref}")
        if conf.get("dealStatus") != "ACCEPTED":
            raise CapitalErrore(f"Ordine rifiutato: {conf.get('reason') or conf.get('dealStatus')}")
        return {"dealId": conf.get("dealId") or (conf.get("affectedDeals") or [{}])[0].get("dealId"),
                "livello": conf.get("level"), "size": conf.get("size", size)}


def _storico(self, percorso: str, giorni: int) -> list[dict]:
    from datetime import datetime, timedelta, timezone
    da = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%dT%H:%M:%S")
    dati, _ = self._chiama("GET", f"{percorso}?from={da}" + ("&detailed=true" if "activity" in percorso else ""))
    return dati.get("activities") or dati.get("transactions") or []


CapitalDemo.attivita = lambda self, giorni=7: _storico(self, "/history/activity", giorni)
CapitalDemo.transazioni = lambda self, giorni=7: _storico(self, "/history/transactions", giorni)


def arrotonda_size(size: float, passo: float) -> float:
    """Arrotonda PER DIFETTO al passo consentito: mai più rischio di quello del piano."""
    if passo <= 0:
        return size
    dec = max(0, -int(math.floor(math.log10(passo)))) if passo < 1 else 0
    return round(math.floor(size / passo + 1e-9) * passo, dec)


# ------------------------------------------------------------------------------
# SIMULATORE (per le prove senza conto): stesse risposte, niente rete
# ------------------------------------------------------------------------------
class CapitalSimulato(CapitalDemo):
    def __init__(self, saldo: float = 1000.0, prezzi: dict | None = None):
        super().__init__()
        self._saldo, self._pos, self._prezzi = saldo, [], prezzi or {}

    def accedi(self):
        self.cst = self.token = "simulato"

    def conto(self):
        return {"valuta": "EUR", "saldo": self._saldo, "pl_aperto": 0.0, "disponibile": self._saldo}

    def posizioni(self):
        return list(self._pos)

    def mercato(self, epic):
        p = self._prezzi.get(epic, 100.0)
        return {"epic": epic, "nome": epic, "valuta": "USD", "min_size": 0.01, "passo": 0.01, "max_size": 1000,
                "min_distanza_stop": 0, "aperto": True, "bid": p - 0.05, "offer": p + 0.05}

    def transazioni(self, giorni=7):
        import json, os
        return json.loads(os.environ.get("TRANS_SIM", "[]"))

    def attivita(self, giorni=7):
        return []

    def sposta_stop(self, deal_id, stop, tp=None):
        for p in self._pos:
            if p["dealId"] == deal_id:
                p["stop"] = stop

    def compra(self, epic, size, stop, tp):
        m = self.mercato(epic)
        self._pos.append({"epic": epic, "nome": epic, "dealId": f"SIM{len(self._pos) + 1}", "size": size,
                          "direzione": "BUY", "livello": m["offer"], "stop": stop, "tp": tp, "upl": 0, "bid": m["bid"]})
        return {"dealId": f"SIM{len(self._pos)}", "livello": m["offer"], "size": size}
