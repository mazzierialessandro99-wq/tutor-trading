"""
EVENTI E NOTIZIE — quello che i prezzi non dicono in anticipo.

  • conti trimestrali delle azioni: niente nuove operazioni nei 3 giorni prima (il prezzo può saltare oltre lo stop)
  • decisioni sui tassi della Fed: niente nuove operazioni su indici USA, valute e oro dal giorno prima
  • tensione sui mercati: con il VIX (l'"indice della paura") sopra 30 il bot ti avvisa. Solo avviso: nella prova sul
    passato (prova_filtri.py) dimezzare il rischio faceva guadagnare meno senza ridurre le discese
  • titoli delle ultime notizie di un mercato, per informarti (NON decidono le operazioni)
Le date della Fed sono quelle pubblicate dalla Fed: vanno aggiunte a mano ogni anno (quelle del 2027 a dicembre).
"""
from __future__ import annotations

import datetime as dt

GIORNI_PRIMA_CONTI = 3
VIX_SOGLIA = 30.0

# giorno dell'annuncio (secondo giorno della riunione) — calendario ufficiale 2026
FED = [dt.date(2026, 1, 28), dt.date(2026, 3, 18), dt.date(2026, 4, 29), dt.date(2026, 6, 17),
       dt.date(2026, 7, 29), dt.date(2026, 9, 16), dt.date(2026, 10, 28), dt.date(2026, 12, 9)]
# annunci passati, servono solo per le prove sul passato
FED_STORICHE = [dt.date(*x) for x in [
    (2023, 2, 1), (2023, 3, 22), (2023, 5, 3), (2023, 6, 14), (2023, 7, 26), (2023, 9, 20), (2023, 11, 1), (2023, 12, 13),
    (2024, 1, 31), (2024, 3, 20), (2024, 5, 1), (2024, 6, 12), (2024, 7, 31), (2024, 9, 18), (2024, 11, 7), (2024, 12, 18),
    (2025, 1, 29), (2025, 3, 19), (2025, 5, 7), (2025, 6, 18), (2025, 7, 30), (2025, 9, 17), (2025, 10, 29), (2025, 12, 10)]] + FED
SENSIBILI_FED = {"^GSPC", "^NDX", "^DJI", "^RUT", "EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X", "GC=F", "SI=F"}


def is_azione(ticker: str) -> bool:
    return not (ticker.startswith("^") or "=" in ticker or ticker.endswith("-USD") or ticker == "FTSEMIB.MI")


def prossimi_conti(ticker: str) -> dt.date | None:
    """Data dei prossimi conti trimestrali (da Yahoo), se nota."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar or {}
        date = cal.get("Earnings Date") or []
        date = [d.date() if hasattr(d, "date") and callable(d.date) else d for d in date]
        futuri = sorted(d for d in date if isinstance(d, dt.date) and d >= dt.date.today())
        return futuri[0] if futuri else None
    except Exception:
        return None


def evento_vicino(ticker: str, oggi: dt.date, cache: dict | None = None) -> str | None:
    """Motivo per NON aprire oggi su questo mercato, oppure None. cache: {ticker: {"giorno", "conti"}} (una lettura al giorno)."""
    for f in FED:
        if ticker in SENSIBILI_FED and 0 <= (f - oggi).days <= 1:
            return f"la Fed decide sui tassi il {f:%d/%m}: il mercato può fare salti improvvisi"
    if not is_azione(ticker):
        return None
    if cache is not None and cache.get(ticker, {}).get("giorno") == str(oggi):
        conti = cache[ticker].get("conti")
        conti = dt.date.fromisoformat(conti) if conti else None
    else:
        conti = prossimi_conti(ticker)
        if cache is not None:
            cache[ticker] = {"giorno": str(oggi), "conti": str(conti) if conti else None}
    if conti and 0 <= (conti - oggi).days <= GIORNI_PRIMA_CONTI:
        return f"i conti trimestrali escono il {conti:%d/%m}: il prezzo può saltare oltre lo stop in una notte"
    return None


def notizie(ticker: str, n: int = 5) -> list[dict]:
    """Ultimi titoli da Yahoo Finance: [{titolo, fonte, link, data}]. Vuota se non disponibili."""
    try:
        import yfinance as yf
        grezze = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for x in grezze:
        c = x.get("content", x)
        titolo = c.get("title")
        if not titolo:
            continue
        link = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link", "")
        fonte = (c.get("provider") or {}).get("displayName") or c.get("publisher", "")
        data = c.get("pubDate") or c.get("providerPublishTime")
        try:
            data = dt.datetime.fromtimestamp(data) if isinstance(data, (int, float)) else dt.datetime.fromisoformat(str(data).replace("Z", "+00:00"))
        except Exception:
            data = None
        out.append({"titolo": titolo, "fonte": fonte, "link": link, "data": data})
        if len(out) >= n:
            break
    return out
