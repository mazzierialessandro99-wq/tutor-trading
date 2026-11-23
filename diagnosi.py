"""
DIAGNOSI — controlla che il bot sia pronto sul conto DEMO, senza aprire nessuna operazione.

Per ogni mercato sorvegliato verifica:
  • che lo strumento esista su Capital.com (epic) e sia negoziabile
  • che il prezzo di Capital.com sia coerente con quello che usiamo per i segnali
  • che con il capitale e il rischio del piano si possa aprire almeno la quantità minima
Stampa anche saldo e posizioni aperte del Demo.

Uso (su GitHub): Actions -> Diagnosi -> Run workflow
"""
from __future__ import annotations

import capital as C
import logica as L
import sentinella as S


def main():
    piano = L.carica_piano()
    capitale = float(piano.get("capitale", 1000))
    print(f"Piano: capitale {capitale:.0f} € · rischio {piano.get('rischio_per_operazione')}% "
          f"(cripto {piano.get('rischio_cripto')}%) · max {piano.get('max_posizioni_aperte')} posizioni · "
          f"modalità {piano.get('modalita')} · obiettivo {piano.get('obiettivo', '-')} €")
    if not C.credenziali_presenti():
        print("❌ Mancano le chiavi Capital.com nei Secrets.")
        return
    b = C.CapitalDemo()
    b.accedi()
    print("✅ Accesso al conto DEMO riuscito")
    c = b.conto()
    print(f"Conto: valuta {c['valuta']} · saldo {c['saldo']:.2f} · P/L aperto {c['pl_aperto']:.2f} · disponibile {c['disponibile']:.2f}")
    pos = b.posizioni()
    print(f"Posizioni aperte: {len(pos)}")
    for p in pos:
        print(f"   - {p['nome']} ({p['epic']}): {p['size']} @ {p['livello']} · stop {p['stop']} · tp {p['tp']} · P/L {p['upl']}")

    tickers = [t for t, _ in L.ASSET.values()]
    dati = S.scarica_tutti(tickers + ["EURUSD=X"])
    eurusd = float(dati["EURUSD=X"]["Close"].iloc[-1]) if "EURUSD=X" in dati else 1.08
    print(f"\nDati Yahoo: {len([t for t in tickers if t in dati])}/{len(tickers)} mercati · EUR/USD {eurusd:.4f}\n")
    print(f"{'Mercato':<22}{'Epic':<11}{'Stato':<9}{'Prezzo CC':>11}{'Yahoo':>11}{'Δ%':>7}{'Min':>8}{'Size piano':>12}  Esito")
    ok = 0
    for nome, (ticker, _) in L.ASSET.items():
        m = b.trova(ticker, nome)
        if not m:
            print(f"{nome:<22}{'-':<11}{'':<9}{'':>11}{'':>11}{'':>7}{'':>8}{'':>12}  ❌ strumento non trovato")
            continue
        if ticker not in dati:
            print(f"{nome:<22}{m['epic']:<11}  ⚠️ nessun dato Yahoo")
            continue
        v = L.valuta(L.aggiungi_indicatori(dati[ticker]))
        prezzo = m["offer"] or m["bid"]
        delta = (prezzo / v["close"] - 1) * 100 if prezzo else float("nan")
        cambio = 1.0 if m["valuta"] == "EUR" else eurusd
        rischio_eur = capitale * L.rischio_per(ticker, piano) / 100
        distanza = L.STOP_ATR * v["atr"]
        size = C.arrotonda_size(rischio_eur * cambio / distanza, m["passo"])
        if abs(delta) >= 15:
            esito = "❌ prezzo troppo diverso: controllare l'abbinamento"
        elif size < m["min_size"]:
            minimo = m["min_size"] * distanza / cambio
            esito = f"⚠️ quantità minima: rischierebbe {minimo:.2f} € invece di {rischio_eur:.2f} € (verrà saltato)"
        elif m["valuta"] not in ("EUR", "USD"):
            esito = f"⚠️ valuta {m['valuta']} non gestita"
        else:
            esito = "✅ pronto"
            ok += 1
        stato = "aperto" if m["aperto"] else "chiuso"
        print(f"{nome:<22}{m['epic']:<11}{stato:<9}{prezzo:>11.2f}{v['close']:>11.2f}{delta:>7.1f}{m['min_size']:>8g}{size:>12g}  {esito}")
    print(f"\nRiepilogo: {ok}/{len(L.ASSET)} mercati pronti per l'operatività automatica.")


if __name__ == "__main__":
    main()
