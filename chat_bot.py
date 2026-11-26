"""
CHAT DEL BOT — risponde in italiano usando i dati veri del bot (memoria, ricerca, mercati, tutor).
Nessuna intelligenza artificiale esterna: regole semplici e trasparenti, così non costa niente
e non inventa numeri. Ogni risposta è HTML semplice (grassetti e a capo).
"""
from __future__ import annotations

import re
import unicodedata

import logica as L

SUGGERIMENTI = ["Come va?", "Operazioni aperte", "Cosa c'è di verde oggi?", "Perché non operi?",
                "Come metto lo stop loss?", "Analizza l'oro"]

# parole chiave dei mercati (minuscole, senza accenti) -> nome nella lista dei mercati
ALIAS = {
    "s&p": "S&P 500 (USA)", "sp500": "S&P 500 (USA)", "s&p500": "S&P 500 (USA)", "us500": "S&P 500 (USA)",
    "nasdaq": "Nasdaq 100 (USA)", "us100": "Nasdaq 100 (USA)", "dow": "Dow Jones (USA)", "us30": "Dow Jones (USA)",
    "dax": "DAX (Germania)", "ftse": "FTSE MIB (Italia)", "mib": "FTSE MIB (Italia)", "stoxx": "Euro Stoxx 50",
    "oro": "Oro", "gold": "Oro", "argento": "Argento", "silver": "Argento", "petrolio": "Petrolio WTI",
    "eurusd": "Euro / Dollaro", "euro dollaro": "Euro / Dollaro", "sterlina": "Sterlina / Dollaro",
    "bitcoin": "Bitcoin", "btc": "Bitcoin", "ethereum": "Ethereum", "eth": "Ethereum", "apple": "Apple",
    "microsoft": "Microsoft", "nvidia": "Nvidia", "amazon": "Amazon", "google": "Alphabet (Google)",
    "alphabet": "Alphabet (Google)", "meta": "Meta", "facebook": "Meta", "tesla": "Tesla",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _num(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _euro(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}{_num(abs(x))} €"


def trova_mercato(testo: str) -> str | None:
    t = _norm(testo)
    for chiave in sorted(ALIAS, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(chiave)}(?![a-z])", t):
            return ALIAS[chiave]
    return None


def rispondi(testo: str, ctx: dict) -> str:
    """ctx: memoria (dict|None), ricerca (dict|None), piano (dict), panoramica (list[dict]),
    analizza (funzione nome -> dict|None con semaforo e tutor)."""
    t = _norm(testo)
    m, ric, piano = ctx.get("memoria") or {}, ctx.get("ricerca") or {}, ctx.get("piano") or {}
    palestra, vincitrice = piano.get("palestra"), ric.get("vincitrice")

    def ha(*parole):
        return any(p in t for p in parole)

    # --- un mercato preciso ---
    nome = trova_mercato(testo)
    if nome:
        a = ctx["analizza"](nome)
        if not a:
            return f"Non riesco a leggere i prezzi di <b>{nome}</b> in questo momento. Riprova tra qualche minuto."
        colore = {"VERDE": "🟢 verde", "GIALLO": "🟡 giallo", "ROSSO": "🔴 rosso"}[a["colore"]]
        righe = [f"<b>{nome}</b>: semaforo {colore}. {a['sintesi']}",
                 f"Trend <b>{a['trend']}</b>, momento <b>{a['momento']}</b>, volatilità <b>{a['vol']}</b>."]
        if a["colore"] == "VERDE":
            righe.append(f"Se entri sul Demo: stop consigliato <b>{a['stop_nome']}</b> a {a['stop']}, "
                         f"take profit a {a['tp']}. Trovi i passi completi in <b>Mercati</b> toccando {nome}.")
        else:
            righe.append(f"Cosa fare: {a['consiglio']}")
        return "<br>".join(righe)

    # --- saluti e aiuto ---
    if ha("ciao", "buongiorno", "buonasera", "salve", "ehi", "hey"):
        return ("Ciao! 👋 Sono il tuo bot di trading. Puoi chiedermi <b>come va</b>, le <b>operazioni aperte</b>, "
                "<b>cosa c'è di verde</b> oggi, di analizzare un mercato (es. <i>analizza il Nasdaq</i>) "
                "o di spiegarti stop loss, RSI, leva e gli altri concetti.")
    if ha("aiuto", "cosa sai", "cosa puoi", "help", "comandi"):
        return ("Ecco cosa so fare:<br>• <b>Come va?</b> · il mio stato di oggi<br>• <b>Operazioni aperte</b><br>"
                "• <b>Risultati</b> · capitale e obiettivo<br>• <b>Cosa c'è di verde?</b> · i segnali di oggi<br>"
                "• <b>Analizza l'oro</b> (o qualsiasi mercato della lista)<br>• <b>Perché non operi?</b> · la mia ricerca<br>"
                "• Spiegazioni: <b>stop loss, take profit, RSI, EMA, ATR, leva, rischio, drawdown</b><br>"
                "Su Telegram puoi usare /stato, /resoconto, /stop e /riprendi.")

    # --- stato e risultati ---
    if ha("come va", "come stai", "stato", "cosa fai", "situazione", "tutto bene"):
        if not m:
            return "Non trovo ancora la mia memoria: compare dopo il primo giro del motore."
        modo = ("in <b>palestra sul Demo</b>: opero la strategia di base per studiare il mercato dal vivo" if palestra and not vincitrice
                else "con la regola promossa dalla ricerca" if vincitrice else "in osservazione, senza operare")
        pos = m.get("posizioni") or []
        return (f"Sto lavorando {modo}. Ultimo controllo dei mercati: <b>{str(m.get('ultimo_giro', ''))[11:16]}</b>, "
                f"poi di nuovo tra al massimo 30 minuti.<br>Operazioni aperte: <b>{len(pos)}</b>.")
    if ha("risultat", "guadagn", "perso", "obiettivo", "capitale", "quanto ho", "saldo"):
        storia = m.get("storia") or []
        cap0 = float(m.get("capitale_piano") or piano.get("capitale", 0))
        ob = float(m.get("obiettivo") or piano.get("obiettivo", 0) or 0)
        att = float(storia[-1][1]) if storia else cap0
        quota = (att - cap0) / (ob - cap0) * 100 if ob > cap0 else 0
        return (f"Capitale del bot: <b>{_num(att)} €</b> ({_euro(att - cap0)} dall'inizio).<br>"
                f"Obiettivo: {_num(ob, 0)} € · siamo al <b>{max(quota, 0):.0f}%</b> del percorso.")
    if ha("operazion", "posizion", "aperte", "aperta", "trade"):
        pos = m.get("posizioni") or []
        if not pos:
            return "Non ho operazioni aperte. Aspetto che un semaforo diventi verde: succede in media 2-3 volte al mese."
        righe = [f"• <b>{p.get('nome')}</b>: {p.get('size')} contratti a {p.get('livello')}, "
                 f"stop {p.get('stop')}, take profit {p.get('tp')} · {_euro(float(p.get('upl') or 0))}" for p in pos]
        return f"Ho <b>{len(pos)}</b> operazion{'e' if len(pos) == 1 else 'i'} apert{'a' if len(pos) == 1 else 'e'}:<br>" + "<br>".join(righe)

    # --- segnali di oggi ---
    if ha("verde", "segnal", "cosa compro", "opportunit", "occasion", "consigli"):
        righe = ctx.get("panoramica") or []
        verdi = [r["nome"] for r in righe if r["colore"] == "VERDE"]
        gialli = sum(r["colore"] == "GIALLO" for r in righe)
        if verdi:
            return (f"Oggi sono verdi: <b>{', '.join(verdi)}</b>. Prima di entrare guarda il tutor del mercato "
                    "(stop consigliato e checklist). Ricorda: sono segnali, non certezze.")
        return (f"Oggi nessun semaforo è verde ({gialli} gialli, il resto rossi). Si aspetta: "
                "un giorno senza operazioni non è un giorno perso.")

    # --- ricerca ---
    if ha("ricerca", "perche non", "non operi", "strategia", "vantaggio", "palestra"):
        if vincitrice:
            return (f"La ricerca ha promosso la strategia <b>{vincitrice['strategia']}</b> con take profit 1:{vincitrice['rr']:.0f}: "
                    "ha guadagnato sia sui 20 mercati sia su quelli mai visti, quindi la uso.")
        testo_r = ("Ogni domenica provo 30 combinazioni di regole su 3 anni e 74 mercati, con spread e commissioni notturne. "
                   "Questa settimana <b>nessuna</b> ha guadagnato anche sui mercati che non avevo mai visto: "
                   "vuol dire che il vantaggio non è affidabile.")
        if palestra:
            testo_r += " In <b>palestra sul Demo</b> opero comunque la strategia di base, per raccogliere dati veri."
        return testo_r

    # --- spiegazioni ---
    spiegazioni = [
        (("stop loss", "stop"), "Lo <b>stop loss</b> è il prezzo a cui l'operazione si chiude da sola in perdita. Si decide "
         "<b>prima</b> di entrare: meglio un po' sotto il minimo recente (se è a 1,5-3,5 ATR) oppure a 2 ATR. Mai troppo stretto "
         "(sotto 1 ATR) e <b>mai allontanarlo</b> dopo. La quantità si calcola dallo stop: stop più lontano = meno quote."),
        (("take profit",), "Il <b>take profit</b> è il prezzo a cui si chiude in guadagno. Lo metto al doppio della distanza "
         "dello stop (1:2): così basta vincere circa 1 volta su 3 per non perdere. Accorciarlo per vincere più spesso, "
         "nei test, peggiora i risultati."),
        (("rsi",), "L'<b>RSI</b> misura quanto un prezzo è salito o sceso di recente, da 0 a 100. Sopra 70 è 'tirato', "
         "tra 30 e 45 in un trend positivo indica una pausa: è lì che cerco gli ingressi."),
        (("ema", "media"), "La <b>EMA 200</b> è la media dei prezzi degli ultimi 200 giorni circa. Prezzo sopra = trend positivo, "
         "sotto = negativo. Compro solo sopra."),
        (("atr", "volatilit"), "L'<b>ATR</b> è quanto si muove in media un mercato in una giornata. Lo uso per mettere lo stop "
         "fuori dal 'rumore' normale."),
        (("leva",), "La <b>leva</b> ti fa muovere più soldi di quelli che hai. Non aumenta il guadagno medio: ti fa arrivare "
         "prima allo stop o al conto vuoto. Io calcolo sempre la quantità dal rischio, mai dalla leva disponibile."),
        (("rischio", "1%"), "Rischio al massimo l'<b>1% del capitale</b> per operazione (0,5% sulle cripto). Anche 10 perdite "
         "di fila lasciano il 90% del conto."),
        (("drawdown",), "Il <b>drawdown</b> è quanto il conto scende rispetto al suo massimo precedente. È la discesa che devi "
         "essere pronto a sopportare senza cambiare le regole."),
        (("win rate", "percentuale"), "Il <b>win rate</b> è la percentuale di operazioni vinte. Da solo non conta: conta quanto "
         "guadagni quando vinci rispetto a quanto perdi quando sbagli."),
        (("telegram",), "Su Telegram mi trovi con /stato, /resoconto, /stop (smetto di aprire operazioni) e /riprendi."),
    ]
    for parole, risposta in spiegazioni:
        if ha(*parole):
            return risposta

    return ("Non sono sicuro di aver capito 🤔. Prova con: <i>come va?</i>, <i>operazioni aperte</i>, "
            "<i>cosa c'è di verde oggi?</i>, <i>analizza Bitcoin</i>, <i>cos'è lo stop loss?</i>")
