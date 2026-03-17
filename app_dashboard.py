import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# 1. Page Config
st.set_page_config(page_title="Mtrol Precision Analytics", layout="wide")

# --- CUSTOM CSS FOR FIXED HEIGHT & WEIGHT ---
st.markdown("""
    <style>
    .metric-container {
        text-align: center;
        padding: 15px 10px;
        background-color: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #333;
        min-height: 100px; /* Fixed height for all boxes */
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label {
        font-size: 18px !important; 
        font-weight: 700; /* Heavier weight for Heading */
        color: #FFD700;
        margin-bottom: 8px;
        line-height: 1.2;
    }
    .metric-value {
        font-size: 16px !important;
        font-weight: 400; /* Lighter weight for Numeric Value */
        color: #ffffff;
    }
    /* Remove default streamlit padding above columns */
    .stHorizontalBlock {
        align-items: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURATION ---
MT3_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "ref": 200.0, "max": 303.5447, "min": 0.0, "ppm": "—"},
    "opening": {"unit": "%", "range": [-20, 70], "ref": 100.0, "max": 22.0132, "min": 0.0, "ppm": "2449.99"},
    "p1": {"unit": "bar", "range": [0, 12], "ref": 17.0, "max": 10.6029, "min": 0.0, "ppm": "21455.76"},
    "p2": {"unit": "bar", "range": [0, 12], "ref": 17.0, "max": 10.0592, "min": 0.0, "ppm": "20355.54"}
}

MT4_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "ref": 500.0, "max": 275.1067, "min": 0.0, "ppm": "—"},
    "opening": {"unit": "%", "range": [-20, 70], "ref": 100.0, "max": 19.5011, "min": 0.0, "ppm": "2170.41"},
    "p1": {"unit": "bar", "range": [4, 6], "ref": 17.0, "max": 5.3704, "min": 5.3062, "ppm": "129.91"},
    "p2": {"unit": "bar", "range": [0, 12], "ref": 17.0, "max": 10.7396, "min": 10.5863, "ppm": "310.21"}
}

TEMP_WINDOW = [-20, 70]
START_TIME = "2026-03-11 10:20:00"
END_TIME = "2026-03-13 11:30:00"

@st.cache_data
def load_and_sync(dev_file, temp_file):
    df_t = pd.read_csv(temp_file).dropna(how='all')
    df_t.columns = ['Timestamp', 'Temp']
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    df_d = pd.read_csv(dev_file)
    time_col = next((c for c in df_d.columns if "time" in c.lower()), "Time Stamp")
    df_d[time_col] = pd.to_datetime(df_d[time_col], errors='coerce')
    
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_d.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(time_col).mean().sort_index()
    combined = pd.concat([df_d, df_t], axis=1)
    combined = combined.loc[START_TIME : END_TIME].reset_index().rename(columns={'index': 'Full_Time'})
    return combined

# --- UI ---
st.title("Mtrol Precision Analytics")

st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber CSV", type=['csv'])

if dev_upload and temp_upload:
    try:
        df_full = load_and_sync(dev_upload, temp_upload)
        is_mt4 = "MT4" in dev_upload.name.upper()
        lookup = MT4_CONFIG if is_mt4 else MT3_CONFIG
        
        options = [c for c in df_full.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if options:
            selected = st.sidebar.selectbox("Choose curve to plot", options)
            std = lookup["p1" if "p1" in selected.lower() else "p2" if "p2" in selected.lower() else "flow" if "flow" in selected.lower() else "opening"]

            # Metrics Row (No Header Line)
            cols = st.columns(5)
            t_min_obs = df_full['Temp'].min()
            t_max_obs = df_full['Temp'].max()
            
            metrics_data = [
                (f"Min {selected}", f"{std['min']:.4f}"),
                (f"Max {selected}", f"{std['max']:.4f}"),
                ("Min Temp", f"{t_min_obs:.1f} °C" if pd.notnull(t_min_obs) else "—"),
                ("Max Temp", f"{t_max_obs:.1f} °C" if pd.notnull(t_max_obs) else "—"),
                (f"{selected} PPM", std["ppm"])
            ]

            for i, (label, val) in enumerate(metrics_data):
                with cols[i]:
                    st.markdown(f"""
                        <div class="metric-container">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value">{val}</div>
                        </div>
                    """, unsafe_allow_html=True)

            # --- PLOTTING ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scattergl(x=df_full['Full_Time'], y=df_full[selected], mode='markers', 
                                       marker=dict(size=2.5, color="#00CCFF", opacity=0.4), name=f"{selected} (1s)"), secondary_y=False)

            temp_plot_df = df_full.dropna(subset=['Temp'])
            fig.add_trace(go.Scattergl(x=temp_plot_df['Full_Time'], y=temp_plot_df['Temp'], mode='markers', 
                                       marker=dict(size=6, color="#FFD700", symbol='diamond'), name="Temp (2-min)"), secondary_y=True)

            fig.update_layout(template="plotly_dark", height=600, hovermode="x unified",
                              xaxis=dict(title="Timeline", rangeslider=dict(visible=True)),
                              yaxis=dict(title=f"<b>{selected}</b>", range=std["range"], color="#00CCFF", fixedrange=True),
                              yaxis2=dict(title="<b>Temp (°C)</b>", range=TEMP_WINDOW, side='right', color="#FFD700", fixedrange=True),
                              legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
                              margin=dict(t=20)) # Reduced top margin since header is gone
            st.plotly_chart(fig, use_container_width=True)

            # --- CLEANED DATASET TABLE ---
            st.divider()
            st.subheader("📄 Original Synced Dataset")
            df_display = df_full.fillna("—")
            st.dataframe(df_display, use_container_width=True, height=400)
            
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload CSV files to begin.")
