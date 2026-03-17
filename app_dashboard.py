import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# 1. Page Config
st.set_page_config(page_title="Mtrol Precision Analytics", layout="wide")

# --- SIDEBAR LOGO ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

# --- CONFIGURATION: RANGES & TARGETS ---
MT3_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "dtick": 20, "ref": 200.0, "target_ppm": "N/A"},
    "opening": {"unit": "%", "range": [-20, 70], "dtick": 10, "ref": 100.0, "target_ppm": 2449.99},
    "p1": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 21455.76},
    "p2": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 20355.54}
}

MT4_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "dtick": 20, "ref": 500.0, "target_ppm": "N/A"},
    "opening": {"unit": "%", "range": [-20, 70], "dtick": 10, "ref": 100.0, "target_ppm": 2170.41},
    "p1": {"unit": "bar", "range": [4, 6], "dtick": 0.5, "ref": 17.0, "target_ppm": 129.91},
    "p2": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 310.21}
}

TEMP_WINDOW = [-20, 70]
TEMP_DELTA_FIXED = 89.85
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
    combined['Temp'] = combined['Temp'].interpolate(method='time')
    combined = combined.loc[START_TIME : END_TIME].reset_index().rename(columns={'index': 'Full_Time'})
    return combined

# --- UI ---
st.title("Mtrol Precision Analytics - Cloud View")

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
            key = "p1" if "p1" in selected.lower() else "p2" if "p2" in selected.lower() else "flow" if "flow" in selected.lower() else "opening"
            std = lookup[key]

            # Calculation Stats
            p_min, p_max = df_full[selected].min(), df_full[selected].max()
            t_min, t_max = df_full['Temp'].min(), df_full['Temp'].max()
            drift = p_max - p_min
            calc_ppm = (drift * 1000000) / (TEMP_DELTA_FIXED * std["ref"])

            # --- HORIZONTAL METRICS AT TOP ---
            st.markdown("### Analysis Summary")
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            
            # Parameter Stats
            col1.metric(f"Min {selected}", f"{p_min:.3f}")
            col2.metric(f"Max {selected}", f"{p_max:.3f}")
            col3.metric("Calculated PPM", f"{calc_ppm:.2f}")
            
            # Temp Stats
            col4.metric("Min Temp", f"{t_min:.1f} °C")
            col5.metric("Max Temp", f"{t_max:.1f} °C")
            col6.metric("Target PPM", f"{std['target_ppm']}")

            # --- PLOTTING ---
            display_df = df_full.iloc[::2] if len(df_full) > 20000 else df_full
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(go.Scattergl(
                x=display_df['Full_Time'], y=display_df[selected], 
                mode='markers', marker=dict(size=3, color="#00CCFF", opacity=0.6),
                name=f"{selected}"
            ), secondary_y=False)

            fig.add_trace(go.Scattergl(
                x=display_df['Full_Time'], y=display_df['Temp'], 
                mode='lines', line=dict(color="#FFD700", dash='dot', width=2),
                name="Chamber Temp"
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600, hovermode="x unified",
                xaxis=dict(title="Timeline", rangeslider=dict(visible=True)),
                yaxis=dict(title=f"<b>{selected}</b>", range=std["range"], color="#00CCFF", fixedrange=True),
                yaxis2=dict(title="<b>Temp (°C)</b>", range=TEMP_WINDOW, side='right', color="#FFD700", fixedrange=True),
                legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center")
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- RAW DATASET AT BOTTOM ---
            st.divider()
            st.subheader("📄 Original Synced Dataset")
            st.dataframe(df_full, use_container_width=True, height=400)
            
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload CSV files to begin analysis.")
