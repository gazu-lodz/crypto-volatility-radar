import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="Live Crypto Pulse",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        padding: 16px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# Mapowanie par Krakena na czytelne symbole
PAIRS_MAP = {
    "BTC/USD": {"pair": "XBTUSD", "ohlc_key": "XXBTZUSD"},
    "ETH/USD": {"pair": "ETHUSD", "ohlc_key": "XETHZUSD"},
    "SOL/USD": {"pair": "SOLUSD", "ohlc_key": "SOLUSD"},
    "XRP/USD": {"pair": "XRPUSD", "ohlc_key": "XXRPZUSD"},
    "ADA/USD": {"pair": "ADAUSD", "ohlc_key": "ADAUSD"}
}

INTERVAL_MAP = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60
}

def fetch_kraken_tickers():
    pairs_param = ",".join([v["pair"] for v in PAIRS_MAP.values()])
    url = f"https://api.kraken.com/0/public/Ticker?pair={pairs_param}"
    res = requests.get(url, timeout=5)
    res.raise_for_status()
    result = res.json().get("result", {})
    
    rows = []
    for label, info in PAIRS_MAP.items():
        # Znajdź wpis w odpowiedzi (Kraken dopasowuje czasem prefiksy Z/X)
        match = next((v for k, v in result.items() if info["pair"] in k or k in (info["pair"], info["ohlc_key"])), None)
        if match:
            last_price = float(match["c"][0])
            open_price = float(match["o"])
            high_price = float(match["h"][1])
            low_price = float(match["l"][1])
            volume = float(match["v"][1])
            change_pct = ((last_price - open_price) / open_price) * 100 if open_price > 0 else 0.0
            
            rows.append({
                "Para": label,
                "lastPrice": last_price,
                "priceChangePercent": change_pct,
                "highPrice": high_price,
                "lowPrice": low_price,
                "volume": volume
            })
    return pd.DataFrame(rows)

def fetch_kraken_ohlc(symbol_label: str, interval_str: str = "1m"):
    pair_kraken = PAIRS_MAP[symbol_label]["pair"]
    interval_val = INTERVAL_MAP.get(interval_str, 1)
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair_kraken}&interval={interval_val}"
    res = requests.get(url, timeout=5)
    res.raise_for_status()
    data = res.json().get("result", {})
    
    # Wyciągnij klucz zawierający tablicę świec (z pominięciem klucza 'last')
    candle_key = next((k for k in data.keys() if k != "last"), None)
    raw_candles = data.get(candle_key, [])[-60:]
    
    df = pd.DataFrame(raw_candles, columns=[
        "time", "open", "high", "low", "close", "vwap", "volume", "count"
    ])
    df["time"] = pd.to_datetime(df["time"], unit="s")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    
    df["sma_10"] = df["close"].rolling(window=10).mean()
    return df

# Panel boczny
st.sidebar.title("⚡ Konfiguracja Live")
selected_symbol = st.sidebar.selectbox("Wybierz parę walutową", list(PAIRS_MAP.keys()), index=0)
selected_interval = st.sidebar.selectbox("Interwał świec", list(INTERVAL_MAP.keys()), index=0)
volatility_threshold = st.sidebar.slider("Próg alertu zmienności (%)", 1.0, 15.0, 4.0, 0.5)

st.title("⚡ Live Crypto & Volatility Radar")
st.caption("Strumieniowy monitor rynku kryptowalut w czasie rzeczywistym (Kraken Global REST API).")

@st.fragment(run_every="5s")
def render_live_dashboard():
    try:
        tickers_df = fetch_kraken_tickers()
        ohlc_df = fetch_kraken_ohlc(selected_symbol, selected_interval)
    except Exception as e:
        st.error(f"Błąd połączenia z API: {e}")
        return

    # Kafelki metryk na samej górze
    cols = st.columns(len(PAIRS_MAP))
    for idx, label in enumerate(PAIRS_MAP.keys()):
        row_match = tickers_df[tickers_df["Para"] == label]
        if not row_match.empty:
            row = row_match.iloc[0]
            price = row["lastPrice"]
            change = row["priceChangePercent"]
            cols[idx].metric(
                label=label,
                value=f"${price:,.2f}" if price >= 1 else f"${price:.4f}",
                delta=f"{change:+.2f}%"
            )

    st.divider()

    col_chart, col_stats = st.columns([2.2, 1])

    with col_chart:
        st.subheader(f"Wykres na żywo: {selected_symbol} ({selected_interval})")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=ohlc_df["time"],
            open=ohlc_df["open"],
            high=ohlc_df["high"],
            low=ohlc_df["low"],
            close=ohlc_df["close"],
            name="Cena"
        ))
        fig.add_trace(go.Scatter(
            x=ohlc_df["time"],
            y=ohlc_df["sma_10"],
            mode="lines",
            line=dict(color="#38bdf8", width=2),
            name="SMA (10)"
        ))
        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15,23,42,0.6)"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_stats:
        st.subheader("Radar Zmienności")
        tickers_df["range_pct"] = ((tickers_df["highPrice"] - tickers_df["lowPrice"]) / tickers_df["lowPrice"]) * 100

        alerts = tickers_df[tickers_df["priceChangePercent"].abs() >= volatility_threshold]
        if not alerts.empty:
            for _, alert_row in alerts.iterrows():
                st.warning(
                    f"**Alert {alert_row['Para']}**: ruch o {alert_row['priceChangePercent']:+.2f}% "
                    f"(Rozpiętość H/L: {alert_row['range_pct']:.2f}%)"
                )
        else:
            st.success("Brak anomalii zmienności.")

        display_df = tickers_df[["Para", "lastPrice", "priceChangePercent", "range_pct"]].copy()
        display_df.columns = ["Para", "Cena ($)", "Zmiana (%)", "Spread H/L (%)"]
        st.dataframe(display_df.style.format({
            "Cena ($)": "{:.2f}",
            "Zmiana (%)": "{:+.2f}%",
            "Spread H/L (%)": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

        st.caption(f"Ostatnia synchronizacja: {datetime.now().strftime('%H:%M:%S')}")

render_live_dashboard()
