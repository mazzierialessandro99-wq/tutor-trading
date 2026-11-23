# 📈 Tutor di Trading

Dashboard personale di **analisi e formazione** sul trading, fatta con Python e Streamlit.

**Non invia ordini.** Gli ordini li inserisci tu, a mano, sul conto **demo** del tuo broker,
seguendo le istruzioni che la dashboard mostra a schermo.

## Le schede

| Scheda | Stato | Cosa fa |
|---|---|---|
| 🎓 Regole d'oro | ✅ pronta | Rischio, EMA 200 / RSI / ATR, Stop Loss e Take Profit, regola dell'1%, calcolatrice della posizione |
| 🚦 Analisi e segnali | ✅ pronta | Asset da yfinance, grafico con indicatori, semaforo, istruzioni passo passo |
| 🧪 Verifica sul passato | 🚧 in costruzione | Backtest sugli ultimi 3 anni, drawdown massimo, win rate |
| 🛰️ Sentinella | ✅ attiva | Controlla 20 mercati ogni 30 minuti (GitHub Actions) e avvisa su Telegram |
| 🤖 Modalità automatica | 🔑 in attesa della chiave API | Apre operazioni da sola, SOLO sul conto Demo Capital.com, con i limiti del piano. Comandi Telegram: /stato /stop /riprendi |

## Usarla dal telefono (senza PC)

È pubblicata su **Streamlit Community Cloud** (gratis): si apre dal browser del telefono.
Ogni modifica caricata su questo repository aggiorna l'app da sola.

## Usarla sul PC (facoltativo)

```
pip install -r requirements.txt
streamlit run app.py
```

Si apre su `http://localhost:8501`.

---

Scopo didattico. Non costituisce consulenza finanziaria.
