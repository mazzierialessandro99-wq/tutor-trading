"""
TUTOR DI TRADING — dashboard personale (solo analisi e formazione).
NON invia ordini: gli ordini li inserisci tu, a mano, sul conto DEMO del tuo broker.

Avvio:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Tutor di Trading", page_icon="📈", layout="centered")

st.title("📈 Tutor di Trading")
st.caption("Assistente personale di analisi e formazione. **Non invia ordini**: decidi e operi sempre tu, su conto demo.")

tab1, tab2, tab3 = st.tabs(["🎓 Regole d'oro", "🚦 Analisi e segnali", "🧪 Verifica sul passato"])


# ==============================================================================
# TAB 1 — PERCHÉ E REGOLE D'ORO
# ==============================================================================
with tab1:
    st.header("Perché e regole d'oro")
    st.write("Leggi questa scheda **prima** di guardare i segnali. Sono le regole che ti tengono in gioco.")

    # --- 1. Rischio zero non esiste -------------------------------------------
    with st.expander("1️⃣  Perché non esiste “rischio zero, guadagno massimo”", expanded=True):
        st.markdown(
            """
Nei mercati **nessuno sa cosa farà il prezzo domani**. Neanche le banche, neanche gli algoritmi.
Ogni strategia ha operazioni vincenti e operazioni perdenti: chi promette guadagni sicuri
ti sta vendendo qualcosa.

Rischio e rendimento vanno **sempre insieme**: per poter guadagnare devi accettare di poter perdere.
La differenza tra chi sopravvive e chi brucia il conto non è indovinare sempre,
ma **perdere poco quando sbagli**. Questa si chiama **gestione del rischio**.
"""
        )
        st.markdown("**Perché le perdite grandi sono così pericolose:** per recuperarle serve molto di più.")
        perdite = [10, 20, 30, 50, 75, 90]
        df_rec = pd.DataFrame({
            "Se perdi": [f"−{p}%" for p in perdite],
            "Per tornare in pari ti serve": [f"+{p / (100 - p) * 100:.0f}%" for p in perdite],
        })
        st.dataframe(df_rec, hide_index=True, use_container_width=True)
        st.info("Perdere il 50% significa dover poi **raddoppiare** il capitale solo per tornare al punto di partenza.")

    # --- 2. Gli indicatori ----------------------------------------------------
    with st.expander("2️⃣  Gli indicatori che usiamo: EMA 200, RSI, ATR"):
        st.markdown(
            """
Un indicatore è un **calcolo fatto sui prezzi passati** che ci aiuta a leggere il grafico.
Non predice il futuro: ci dà un quadro ordinato della situazione.

| Indicatore | A cosa serve | Come lo leggiamo |
|---|---|---|
| **EMA 200** | **Trend** (la direzione di fondo) | Prezzo **sopra** la linea → trend positivo. **Sotto** → trend negativo: non compriamo |
| **RSI (14)** | **Timing** (il momento) | Va da 0 a 100. Sotto **30-40** il prezzo è sceso molto di recente: possibile occasione *se il trend è positivo*. Sopra **70** è “tirato”: meglio non inseguirlo |
| **ATR (14)** | **Volatilità** (quanto si muove) | È l'escursione media di una candela. Ci dice **quanto largo mettere lo stop** per non farci buttare fuori dal rumore |
"""
        )
        st.markdown("**Esempio illustrativo** (prezzi inventati): il prezzo sta sopra la sua EMA 200, quindi il trend è positivo.")
        rng = np.random.default_rng(7)
        n = 400
        prezzo = 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.012, n)))
        s = pd.Series(prezzo)
        ema = s.ewm(span=200, adjust=False).mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=s, name="Prezzo", line=dict(width=1.5)))
        fig.add_trace(go.Scatter(y=ema, name="EMA 200", line=dict(width=2.5, dash="dash")))
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h", y=1.1), xaxis_title="giorni", yaxis_title="prezzo")
        st.plotly_chart(fig, use_container_width=True)

    # --- 3. Stop Loss, Take Profit, regola dell'1% ----------------------------
    with st.expander("3️⃣  Stop Loss, Take Profit e la regola dell'1%"):
        st.markdown(
            """
- **Stop Loss (SL)**: il prezzo a cui l'operazione si **chiude da sola in perdita**.
  Lo decidi *prima* di entrare, a mente fredda. È la tua cintura di sicurezza.
- **Take Profit (TP)**: il prezzo a cui l'operazione si **chiude da sola in guadagno**.
- **Rapporto Rischio/Rendimento 1:2**: il TP è lontano dall'entrata **il doppio** dello SL.
  Così anche vincendo solo **4 operazioni su 10** il conto può restare in attivo.

**La regola dell'1%:** su una singola operazione non rischi mai più dell'**1% del capitale**.
Con 1.000 € significa al massimo **10 €** di perdita se tocca lo stop.
Anche 10 perdite di fila (capita!) ti lasciano circa il 90% del capitale.

La quantità da comprare **non si sceglie a sentimento**, si calcola:
"""
        )
        st.latex(r"\text{quote} = \frac{\text{capitale} \times 1\%}{\text{prezzo di entrata} - \text{stop loss}}")

        st.markdown("**Prova tu** — calcolatrice della posizione:")
        c1, c2 = st.columns(2)
        cap = c1.number_input("Capitale (€)", min_value=100.0, value=1000.0, step=100.0, key="t1_cap")
        rischio_pct = c2.number_input("Rischio (%)", min_value=0.1, max_value=2.0, value=1.0, step=0.1, key="t1_risk")
        c3, c4 = st.columns(2)
        entrata = c3.number_input("Prezzo di entrata", min_value=0.01, value=50.0, step=0.5, key="t1_in")
        stop = c4.number_input("Stop Loss", min_value=0.01, value=48.0, step=0.5, key="t1_sl")

        if stop >= entrata:
            st.error("Per un acquisto lo Stop Loss deve stare **sotto** il prezzo di entrata.")
        else:
            rischio_eur = cap * rischio_pct / 100
            dist = entrata - stop
            quote = rischio_eur / dist
            impegno = quote * entrata
            tp = entrata + 2 * dist
            if impegno > cap:  # non si può impegnare più di quanto si ha
                quote = cap / entrata
                impegno = cap
            m1, m2, m3 = st.columns(3)
            m1.metric("Rischio massimo", f"{rischio_eur:.2f} €")
            m2.metric("Quote", f"{quote:.2f}")
            m3.metric("Capitale impegnato", f"{impegno:.0f} €")
            st.success(
                f"Compri **{quote:.2f} quote** a **{entrata:.2f}**, Stop Loss a **{stop:.2f}**, "
                f"Take Profit a **{tp:.2f}** (1:2). Se va male perdi circa **{quote * dist:.2f} €**, "
                f"se va bene guadagni circa **{quote * dist * 2:.2f} €**."
            )
            st.caption("Le quote frazionarie (es. 4,37) si possono comprare solo su alcuni broker: altrimenti arrotonda **per difetto**.")

    # --- 4. Regole d'oro riassunte --------------------------------------------
    with st.expander("4️⃣  Le regole d'oro in una schermata"):
        st.markdown(
            """
1. **Prima la demo.** Almeno 2-3 mesi e 30+ operazioni su conto demo prima di pensare a soldi veri.
2. **Mai più dell'1%** del capitale a rischio su una singola operazione.
3. **Stop Loss sempre**, impostato *nello stesso momento* in cui apri l'operazione. Mai spostarlo per “dare più spazio”.
4. **Solo a favore del trend**: se il semaforo è rosso, non si opera. Punto.
5. **Niente vendetta**: dopo 3 perdite di fila, stop per la giornata.
6. **Tieni un diario**: data, asset, perché sei entrato, com'è finita. È così che si impara.
7. **Questa app è un tutor, non un oracolo.** I segnali possono sbagliare: per questo esiste lo stop.
"""
        )
        st.warning("Questa dashboard ha scopo **didattico** e non costituisce consulenza finanziaria.")


# ==============================================================================
# TAB 2 e TAB 3 — in costruzione (prossimi passi)
# ==============================================================================
with tab2:
    st.header("Analisi e segnali operativi")
    st.info("🚧 In costruzione: è il prossimo passo.")

with tab3:
    st.header("Verifica sul passato")
    st.info("🚧 In costruzione: arriva dopo la scheda Analisi.")
