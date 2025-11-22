# app.py – Enhanced UI with modern design, better layout, and improved UX
import streamlit as st
import pandas as pd
import io
import time
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

from ingestion import Ingestor
from storage import Storage
from analytics import AnalyticsEngine
from alerts import AlertEngine

# Page config with custom theme
st.set_page_config(
    page_title="Quant Analytics Platform",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Real-time quantitative analytics for statistical arbitrage"
    }
)

# Enhanced styling with modern design
st.markdown("""
    <style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles */
    * {
        font-family: 'Inter', sans-serif;
    }
    
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100%;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0f1419 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    section[data-testid="stSidebar"] .stMarkdown {
        color: #e4e7eb;
    }
    
    /* Headers */
    h1 {
        font-weight: 700;
        font-size: 2.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    h2 {
        font-weight: 600;
        font-size: 1.5rem;
        color: #cbd5e1;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid rgba(102, 126, 234, 0.3);
    }
    
    h3 {
        font-weight: 600;
        font-size: 1.2rem;
        color: #94a3b8;
    }
    
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #667eea;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.875rem;
        font-weight: 500;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        padding: 1.25rem;
        border-radius: 12px;
        border: 1px solid rgba(102, 126, 234, 0.2);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 8px;
        border: none;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    /* Primary buttons */
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* Input fields */
    .stTextInput>div>div>input,
    .stNumberInput>div>div>input,
    .stSelectbox>div>div>select {
        border-radius: 8px;
        border: 1px solid rgba(102, 126, 234, 0.3);
        background: rgba(15, 20, 25, 0.5);
        color: #e4e7eb;
        padding: 0.5rem;
    }
    
    .stTextInput>div>div>input:focus,
    .stNumberInput>div>div>input:focus,
    .stSelectbox>div>div>select:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
    }
    
    /* Dataframe styling */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid rgba(102, 126, 234, 0.2);
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: rgba(102, 126, 234, 0.1);
        border-radius: 8px;
        border: 1px solid rgba(102, 126, 234, 0.2);
        font-weight: 600;
    }
    
    /* Info/Success/Warning boxes */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
        padding: 1rem;
    }
    
    /* Divider */
    hr {
        margin: 2rem 0;
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.3), transparent);
    }
    
    /* File uploader */
    [data-testid="stFileUploader"] {
        background: rgba(102, 126, 234, 0.05);
        border: 2px dashed rgba(102, 126, 234, 0.3);
        border-radius: 12px;
        padding: 1rem;
    }
    
    /* Checkbox */
    .stCheckbox {
        padding: 0.5rem;
    }
    
    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .status-active {
        background: rgba(34, 197, 94, 0.2);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    
    .status-inactive {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    
    .status-warning {
        background: rgba(251, 191, 36, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(251, 191, 36, 0.3);
    }
    
    /* Chart container styling */
    .js-plotly-plot {
        border-radius: 12px;
        overflow: hidden;
    }
    
    /* Sidebar section headers */
    .sidebar-section {
        background: rgba(102, 126, 234, 0.1);
        padding: 0.75rem;
        border-radius: 8px;
        margin: 1rem 0 0.5rem 0;
        border-left: 3px solid #667eea;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------- Sidebar controls ----------------
st.sidebar.markdown(
    '<div class="sidebar-section"><h3 style="margin:0; color:#e4e7eb;">⚙️ Configuration</h3></div>',
    unsafe_allow_html=True,
)

symbols_input = st.sidebar.text_input(
    "Trading Pairs",
    value="btcusdt,ethusdt",
    help="Enter comma-separated symbols in lowercase",
)
symbols = [s.strip().lower() for s in symbols_input.split(",") if s.strip()]

col1, col2 = st.sidebar.columns(2)
with col1:
    timeframe = st.selectbox("Timeframe", ["1s", "1min", "5min"], index=1)
with col2:
    rolling_window = st.number_input("Rolling Window", value=30, min_value=2, step=1)

col3, col4 = st.sidebar.columns(2)
with col3:
    z_threshold = st.number_input("Z-Threshold", value=2.0, step=0.1)
with col4:
    primary_symbol = st.selectbox(
        "Primary", options=symbols if symbols else ["btcusdt"]
    )

autorefresh = st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=True)

st.sidebar.markdown(
    '<div class="sidebar-section"><h3 style="margin:0; color:#e4e7eb;">📡 Data Ingestion</h3></div>',
    unsafe_allow_html=True,
)

col_start, col_stop = st.sidebar.columns(2)
with col_start:
    start_btn = st.button("▶️ Start", use_container_width=True, type="primary")
with col_stop:
    stop_btn = st.button("⏹️ Stop", use_container_width=True)

st.sidebar.markdown(
    '<div class="sidebar-section"><h3 style="margin:0; color:#e4e7eb;">📤 Data Management</h3></div>',
    unsafe_allow_html=True,
)

uploaded = st.sidebar.file_uploader(
    "Upload Historical OHLC",
    type=["csv"],
    help="CSV format: ts,symbol,open,high,low,close,volume",
)

col_exp1, col_exp2 = st.sidebar.columns(2)
with col_exp1:
    export_ohlc = st.button("📊 Export OHLC", use_container_width=True)
with col_exp2:
    export_analytics = st.button("📈 Export Analytics", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("💡 **Tip:** Upload historical OHLC data to seed the database instantly")

# ---------------- Backend init ----------------
storage = Storage("ticks.sqlite")
analytics = AnalyticsEngine(storage=storage)
alert_engine = AlertEngine(storage=storage)

if "ingestor" not in st.session_state:
    st.session_state["ingestor"] = Ingestor(storage=storage)
ingestor = st.session_state["ingestor"]

if "alerts_log" not in st.session_state:
    st.session_state["alerts_log"] = []

# ---------------- Ingestion controls ----------------
if start_btn:
    if symbols:
        try:
            ingestor.stop()
        except Exception:
            pass
        time.sleep(0.1)
        st.session_state["ingestor"] = Ingestor(storage=storage)
        ingestor = st.session_state["ingestor"]
        ingestor.start(symbols)
        st.success(f"✅ Ingestion started for: {', '.join(symbols)}")
    else:
        st.warning("⚠️ Please provide at least one symbol")

if stop_btn:
    try:
        ingestor.stop()
    except Exception:
        pass
    st.success("✅ Ingestion stopped")

# ---------------- File upload ingestion ----------------
if uploaded is not None:
    try:
        df_upload = pd.read_csv(uploaded)
        df_upload.columns = [c.lower().strip() for c in df_upload.columns]
        required = {"ts", "symbol", "open", "high", "low", "close"}

        if not required.issubset(set(df_upload.columns)):
            st.sidebar.error("❌ Missing required columns")
        else:
            df_upload["ts_parsed"] = pd.to_datetime(
                df_upload["ts"],
                utc=True,
                infer_datetime_format=True,
                errors="coerce",
            )
            df_good = df_upload.dropna(
                subset=["ts_parsed", "open", "high", "low", "close"]
            )

            if df_good.empty:
                st.sidebar.error("❌ No valid rows found")
            else:
                inserted = 0
                for _, row in df_good.iterrows():
                    try:
                        ts = row["ts_parsed"].to_pydatetime()
                        symbol = str(row["symbol"]).strip().lower()
                        o, h, l, c = (
                            float(row["open"]),
                            float(row["high"]),
                            float(row["low"]),
                            float(row["close"]),
                        )
                        v = (
                            float(row["volume"])
                            if "volume" in row and not pd.isna(row["volume"])
                            else 0.0
                        )
                        storage.insert_ohlc_bar(symbol, ts, o, h, l, c, v)
                        inserted += 1
                    except Exception:
                        continue
                st.sidebar.success(f"✅ Inserted {inserted} OHLC bars")
    except Exception as e:
        st.sidebar.error(f"❌ Upload failed: {str(e)}")

# ---------------- Prepare data ----------------
df_ohlc = analytics.get_resampled_ohlc(symbols, timeframe)

pair_res = None
if len(symbols) >= 2:
    try:
        pair_res = analytics.compute_pair_analytics(
            symbols[0], symbols[1], timeframe=timeframe, rolling=rolling_window
        )
    except Exception:
        pair_res = None

# Compute KPIs
last_z = last_hedge = last_corr = None
if pair_res:
    try:
        df_pair = pair_res.get("df")
        if df_pair is not None and not df_pair.empty:
            zvals = df_pair["zscore"].dropna()
            if not zvals.empty:
                last_z = float(zvals.iat[-1])
        last_hedge = (
            float(pair_res.get("hedge")) if pair_res.get("hedge") is not None else None
        )
        rc = pair_res.get("rolling_corr")
        if rc is not None:
            rc_valid = rc.dropna()
            if not rc_valid.empty:
                last_corr = float(rc_valid.iat[-1])
    except Exception:
        pass

last_tick_time_raw = storage.last_timestamp()
last_tick_display = "—"
if last_tick_time_raw:
    try:
        ts = pd.to_datetime(last_tick_time_raw, utc=True)
        ts_ist = ts.tz_convert("Asia/Kolkata")
        last_tick_display = ts_ist.strftime("%H:%M:%S")
    except Exception:
        last_tick_display = "—"

# ---------------- Header ----------------
st.markdown('<h1>🎯 Quantitative Analytics Platform</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:#94a3b8; font-size:1.1rem; margin-bottom:2rem;">Real-time analytics for statistical arbitrage and market microstructure</p>',
    unsafe_allow_html=True,
)

# ---------------- KPI Dashboard ----------------
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    delta_color = "normal"
    if last_z is not None and abs(last_z) >= z_threshold:
        delta_color = "inverse"
    st.metric(
        "Z-Score",
        f"{last_z:.2f}" if last_z is not None else "—",
        delta=f"Threshold: ±{z_threshold}" if last_z is not None else None,
        delta_color=delta_color,
    )

with kpi2:
    st.metric(
        "Hedge Ratio",
        f"{last_hedge:.4f}" if last_hedge is not None else "—",
        help="OLS regression coefficient between pair",
    )

with kpi3:
    st.metric(
        "Correlation",
        f"{last_corr:.3f}" if last_corr is not None else "—",
        help="Rolling correlation between symbols",
    )

with kpi4:
    st.metric(
        "Last Update",
        last_tick_display,
        help="Last tick timestamp (IST)",
    )

st.markdown("---")

# ---------------- Main Content ----------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Market Data", "🔬 Pair Analytics", "🚨 Alerts", "⚙️ System"]
)

# ================= TAB 1: Market Data =================
with tab1:
    st.markdown("## 📈 Price Action & Volume")

    if df_ohlc.empty:
        st.info(
            "🕐 Waiting for data... Start ingestion or upload historical OHLC to begin"
        )
    else:
        try:
            df_ohlc.index = df_ohlc.index.tz_convert("Asia/Kolkata")
        except Exception:
            try:
                df_ohlc.index = (
                    pd.to_datetime(df_ohlc.index)
                    .tz_localize("UTC")
                    .tz_convert("Asia/Kolkata")
                )
            except Exception:
                pass

        if primary_symbol in df_ohlc["symbol"].unique():
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            p = df_ohlc[df_ohlc["symbol"] == primary_symbol].copy().sort_index()
            p.index = pd.to_datetime(p.index)

            fig = make_subplots(
                rows=2,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.7, 0.3],
                subplot_titles=(
                    f"{primary_symbol.upper()} Price",
                    "Volume (Notional)",
                ),
            )

            fig.add_trace(
                go.Candlestick(
                    x=p.index,
                    open=p["open"],
                    high=p["high"],
                    low=p["low"],
                    close=p["close"],
                    name=primary_symbol.upper(),
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                ),
                row=1,
                col=1,
            )

            for sym in symbols:
                if sym != primary_symbol and sym in df_ohlc["symbol"].unique():
                    s = df_ohlc[df_ohlc["symbol"] == sym].sort_index()
                    s.index = pd.to_datetime(s.index)
                    fig.add_trace(
                        go.Candlestick(
                            x=s.index,
                            open=s["open"],
                            high=s["high"],
                            low=s["low"],
                            close=s["close"],
                            name=sym.upper(),
                            increasing_line_color="#3b82f6",
                            decreasing_line_color="#f97316",
                            opacity=0.7,
                        ),
                        row=1,
                        col=1,
                    )

            p["notional"] = p["close"] * p["volume"]
            colors = [
                "#22c55e" if row["close"] >= row["open"] else "#ef4444"
                for _, row in p.iterrows()
            ]
            fig.add_trace(
                go.Bar(
                    x=p.index,
                    y=p["notional"],
                    name="Volume",
                    marker_color=colors,
                    opacity=0.7,
                ),
                row=2,
                col=1,
            )

            fig.update_layout(
                height=600,
                xaxis_rangeslider_visible=False,
                hovermode="x unified",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )

            fig.update_xaxes(
                showgrid=True, gridwidth=1, gridcolor="rgba(102, 126, 234, 0.1)"
            )
            fig.update_yaxes(
                showgrid=True, gridwidth=1, gridcolor="rgba(102, 126, 234, 0.1)"
            )

            st.plotly_chart(fig, use_container_width=True, key="market_candles")
        else:
            st.warning(f"⚠️ Primary symbol '{primary_symbol}' not available")

# ================= TAB 2: Pair Analytics =================
with tab2:
    st.markdown("## 🔬 Statistical Arbitrage Metrics")

    if len(symbols) < 2:
        st.info("📊 Select at least two symbols to compute pair analytics")
    elif not pair_res:
        minutes_per_bar = {"1s": 1 / 60, "1min": 1, "5min": 5}[timeframe]
        needed_minutes = rolling_window * minutes_per_bar
        st.info(
            f"⏳ Accumulating data... Need ~{needed_minutes:.1f} minutes of bars\n\n"
            f"**Current settings:** {timeframe} timeframe × {rolling_window} window"
        )
    else:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        df_pair = pair_res["df"]
        try:
            df_pair.index = df_pair.index.tz_convert("Asia/Kolkata")
        except Exception:
            try:
                df_pair.index = (
                    pd.to_datetime(df_pair.index)
                    .tz_localize("UTC")
                    .tz_convert("Asia/Kolkata")
                )
            except Exception:
                pass

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        fig.add_trace(
            go.Scatter(
                x=df_pair.index,
                y=df_pair["spread"],
                name="Spread",
                line=dict(color="#60a5fa", width=2),
                fill="tozeroy",
                fillcolor="rgba(96, 165, 250, 0.1)",
            ),
            secondary_y=False,
        )

        fig.add_trace(
            go.Scatter(
                x=df_pair.index,
                y=df_pair["zscore"],
                name="Z-Score",
                line=dict(color="#a78bfa", width=2, dash="dash"),
            ),
            secondary_y=True,
        )

        fig.add_hline(
            y=0,
            line_dash="dot",
            line_color="rgba(148, 163, 184, 0.5)",
            secondary_y=False,
        )
        fig.add_hline(
            y=z_threshold, line_dash="dash", line_color="#ef4444", secondary_y=True
        )
        fig.add_hline(
            y=-z_threshold, line_dash="dash", line_color="#22c55e", secondary_y=True
        )

        fig.update_xaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(102, 126, 234, 0.1)"
        )
        fig.update_yaxes(
            title_text="Spread (Price Units)",
            secondary_y=False,
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(102, 126, 234, 0.1)",
        )
        fig.update_yaxes(
            title_text="Z-Score",
            secondary_y=True,
            showgrid=False,
        )

        fig.update_layout(
            height=450,
            hovermode="x unified",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
        )

        st.plotly_chart(fig, use_container_width=True, key="pair_spread_zscore")

        st.markdown("### 📊 Statistical Summary")

        col_a, col_b, col_c, col_d = st.columns(4)

        zvals = df_pair["zscore"].dropna()
        latest_z = float(zvals.iat[-1]) if not zvals.empty else None
        latest_sp = (
            float(df_pair["spread"].dropna().iat[-1])
            if not df_pair["spread"].dropna().empty
            else None
        )

        with col_a:
            st.metric("Current Spread", f"{latest_sp:.4f}" if latest_sp else "—")
        with col_b:
            st.metric("Current Z-Score", f"{latest_z:.2f}" if latest_z else "—")
        with col_c:
            st.metric(
                "ADF p-value",
                f"{pair_res.get('adf_p'):.4f}" if pair_res.get("adf_p") else "—",
            )
        with col_d:
            cointegration = (
                "✅ Cointegrated"
                if pair_res.get("adf_p") and pair_res.get("adf_p") < 0.05
                else "❌ Not Cointegrated"
            )
            st.markdown(f"**Status:** {cointegration}")

        if latest_z and abs(latest_z) >= z_threshold:
            entry = {
                "time": datetime.utcnow()
                .replace(tzinfo=timezone.utc)
                .isoformat(),
                "type": "zscore",
                "value": latest_z,
                "threshold": z_threshold,
                "symbols": f"{symbols[0]}/{symbols[1]}",
            }
            if not st.session_state["alerts_log"] or st.session_state["alerts_log"][
                -1
            ].get("value") != entry["value"]:
                st.session_state["alerts_log"].append(entry)

# ================= TAB 3: Alerts =================
with tab3:
    st.markdown("## 🚨 Alert Management")

    if st.session_state["alerts_log"]:
        df_alerts = pd.DataFrame(st.session_state["alerts_log"])
        df_alerts["time"] = pd.to_datetime(df_alerts["time"]).dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        st.markdown("### 🔴 Active Alerts")
        for alert in (
            df_alerts.sort_values("time", ascending=False)
            .head(5)
            .to_dict("records")
        ):
            alert_type = (
                "🔴 CRITICAL"
                if abs(alert["value"]) >= alert["threshold"] * 1.5
                else "🟡 WARNING"
            )
            st.markdown(
                f"""
                <div style="background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem;">
                    <strong>{alert_type}</strong> | {alert['symbols']} | Z-Score: <strong>{alert['value']:.2f}</strong><br>
                    <small style="color: #94a3b8;">Time: {alert['time']} | Threshold: ±{alert['threshold']}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("### 📋 Alert History")
        st.dataframe(df_alerts, use_container_width=True, height=300)

        if st.button("🗑️ Clear Alert History", use_container_width=False):
            st.session_state["alerts_log"] = []
            st.rerun()
    else:
        st.info("✅ No alerts triggered. System is monitoring...")

# ================= TAB 4: System =================
with tab4:
    st.markdown("## ⚙️ System Diagnostics")

    col_sys1, col_sys2 = st.columns(2)

    with col_sys1:
        st.markdown("### 📊 Data Statistics")
        df_raw = storage.fetch_recent_ticks(minutes=24 * 60)

        metrics = {
            "Total Ticks (24h)": len(df_raw),
            "Symbols Tracked": len(symbols),
            "Timeframe": timeframe,
            "Rolling Window": rolling_window,
        }

        for key, value in metrics.items():
            st.markdown(f"**{key}:** `{value}`")

    with col_sys2:
        st.markdown("### 🔧 System Status")
        ingestion_status = "🟢 Active" if ingestor.running else "🔴 Stopped"
        st.markdown(f"**Ingestion:** {ingestion_status}")
        st.markdown(
            f"**Auto-refresh:** {'🟢 Enabled' if autorefresh else '🔴 Disabled'}"
        )
        st.markdown(f"**Database:** `ticks.sqlite`")
        st.markdown(f"**Total Rows:** `{storage.count_rows()}`")

    st.markdown("---")

    with st.expander("🔍 Debug Information"):
        st.write("**Raw Ticks (Last 24h):**", len(df_raw))
        if not df_raw.empty:
            st.write("**Ticks per Symbol:**")
            st.write(df_raw.groupby("symbol").size())

        if not df_ohlc.empty:
            st.write("**Resampled Bars:**")
            st.write(df_ohlc.groupby("symbol").size())
            st.write("**Latest Bars:**")
            st.dataframe(df_ohlc.tail(10))

# ================= Exports =================
if export_ohlc:
    df_o = analytics.get_resampled_ohlc(symbols, timeframe)
    if df_o.empty:
        st.warning("⚠️ No OHLC data to export")
    else:
        buf = io.StringIO()
        df_o.to_csv(buf)
        st.download_button(
            "📥 Download OHLC CSV",
            buf.getvalue(),
            file_name=f"ohlc_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

if export_analytics:
    if len(symbols) < 2:
        st.warning("⚠️ Need at least two symbols for analytics export")
    else:
        res_export = analytics.compute_pair_analytics(
            symbols[0], symbols[1], timeframe=timeframe, rolling=rolling_window
        )
        if (
            not res_export
            or res_export.get("df") is None
            or res_export["df"].empty
        ):
            st.warning("⚠️ No analytics data to export")
        else:
            buf = io.StringIO()
            res_export["df"].to_csv(buf)
            st.download_button(
                "📥 Download Analytics CSV",
                buf.getvalue(),
                file_name=f"analytics_{symbols[0]}_{symbols[1]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

# ---------------- Auto-refresh ----------------
if autorefresh:
    st_autorefresh(interval=30_000, key="data_refresh")
    st.sidebar.caption("⏱️ Auto-refresh: every 30s")

if st.sidebar.button("🔄 Manual Refresh Now"):
    st.rerun()


st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #64748b; padding: 2rem 0 1rem 0;">
        <p style="margin: 0; font-size: 0.875rem;">
            <strong>Quantitative Analytics Platform</strong> | Real-time statistical arbitrage monitoring
        </p>
        <p style="margin: 0.5rem 0 0 0; font-size: 0.75rem;">
            Volume displayed as notional (price × quantity) for cross-instrument comparability
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
