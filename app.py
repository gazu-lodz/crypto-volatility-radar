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

# Nowoczesny styl CSS wstrzykiwany do aplikacji
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

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"]

def fetch_24h_tickers():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    filtered = [item for item in data if item["symbol"] in SYMBOLS]
    df = pd.DataFrame(filtered)
    numeric_cols = ["lastPrice", "priceChangePercent", "highPrice", "lowPrice", "quoteVolume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
    return df

def fetch_klines(symbol: str, interval: str = "1m", limit: int = 60):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=5)
    response.raise_for_status()
    raw = response.json()
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    # Wyliczanie prostej średniej kroczącej (SMA 10)
    df["sma_10"] = df["close"].rolling(window=10).mean()
    return df

# Panel boczny
st.sidebar.title("⚡ Konfiguracja Live")
selected_symbol = st.sidebar.selectbox("Wybierz parę walutową", SYMBOLS, index=0)
selected_interval = st.sidebar.selectbox("Interwał świec", ["1m", "5m", "15m", "1h"], index=0)
volatility_threshold = st.sidebar.slider("Próg alertu zmienności 24h (%)", 1.0, 15.0, 4.0, 0.5)

st.title("⚡ Live Crypto & Volatility Radar")
st.caption("Strumieniowy monitor rynku kryptowalut w czasie rzeczywistym (Binance REST API).")

@st.fragment(run_every="5s")
def render_live_dashboard():
    try:
        tickers_df = fetch_24h_tickers()
        klines_df = fetch_klines(selected_symbol, selected_interval)
    except Exception as e:
        st.error(f"Błąd połączenia z API: {e}")
        return

    # Pasek metryk na żywo dla wybranych aktywów
    cols = st.columns(len(SYMBOLS))
    for idx, symbol in enumerate(SYMBOLS):
        row = tickers_df[tickers_df["symbol"] == symbol].iloc[0]
        price = row["lastPrice"]
        change = row["priceChangePercent"]
        cols[idx].metric(
            label=symbol.replace("USDT", " / USDT"),
            value=f"${price:,.2f}" if price >= 1 else f"${price:.4f}",
            delta=f"{change:+.2f}%"
        )

    st.divider()

    # Układ główny: Wykres świecowy + Tabela anomalii i statystyk
    col_chart, col_stats = st.columns([2.2, 1])

    with col_chart:
        st.subheader(f"Wykres na żywo: {selected_symbol} ({selected_interval})")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=klines_df["open_time"],
            open=klines_df["open"],
            high=klines_df["high"],
            low=klines_df["low"],
            close=klines_df["close"],
            name="Cena"
        ))
        fig.add_trace(go.Scatter(
            x=klines_df["open_time"],
            y=klines_df["sma_10"],
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
        st.subheader("Radar Zmienności (24h)")
        tickers_df["range_pct"] = ((tickers_df["highPrice"] - tickers_df["lowPrice"]) / tickers_df["lowPrice"]) * 100
        tickers_df["vol_mln"] = (tickers_df["quoteVolume"] / 1_000_000).round(1)

        # Wykrywanie podwyższonej zmienności
        alerts = tickers_df[tickers_df["priceChangePercent"].abs() >= volatility_threshold]
        if not alerts.empty:
            for _, alert_row in alerts.iterrows():
                st.warning(
                    f"**Alert {alert_row['symbol']}**: ruch o {alert_row['priceChangePercent']:+.2f}% "
                    f"(Rozpiętość 24h: {alert_row['range_pct']:.2f}%)"
                )
        else:
            st.success("Brak przekroczeń progu zmienności.")

        display_df = tickers_df[["symbol", "lastPrice", "priceChangePercent", "range_pct", "vol_mln"]].copy()
        display_df.columns = ["Para", "Cena ($)", "Zmiana 24h (%)", "Spread H/L (%)", "Wolumen (M$)"]
        st.dataframe(display_df.style.format({
            "Cena ($)": "{:.2f}",
            "Zmiana 24h (%)": "{:+.2f}%",
            "Spread H/L (%)": "{:.2f}%",
            "Wolumen (M$)": "{:,.1f} M"
        }), use_container_width=True, hide_index=True)

        st.caption(f"Ostatnia synchronizacja: {datetime.now().strftime('%H:%M:%S')}")

render_live_dashboard()