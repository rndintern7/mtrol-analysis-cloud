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

# --- STRICT CONFIGURATION ---
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
    # Process Chamber Temp Data
    df_t = pd.read_csv(temp_file).dropna(how='all')
    df_t.columns = ['Timestamp', 'Temp']
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # Process Device Data
    df_d = pd.read_csv(dev_file)
    time_col = next((c for c in df_d.columns if "time" in c.lower()), "Time Stamp")
    df_d[time_col] = pd.to_datetime(df_d[time_col], errors='coerce')
    
    # Target parameter names to look for
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_d.columns:
        if any(t.lower() in col.lower() for t in targets):
            # Clean data like "**" or noise
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(time_col).mean().sort_index()
    combined = pd.concat([df_d, df_t], axis=1)
    combined['Temp'] = combined['Temp'].interpolate(method='time')
    
    # Filter for the specific March 11-13 cycle
    combined = combined.loc[START_TIME : END_TIME].reset_index().rename(columns={'index': 'Full_Time'})
    
    # GPU-Optimization for large datasets
    if len(combined) > 40000:
        step = len(combined) // 40000
        combined = combined.iloc[::step]
        
    return combined

# --- UI LOGIC ---
st.title("Mtrol Precision Analytics - Cloud Dashboard")

st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber CSV", type=['csv'])

if dev_upload and temp_upload:
    try:
        df = load_and_sync(dev_upload, temp_upload)
        
        # Version Detection
        is_mt4 = "MT4" in dev_upload.name.upper()
        dev_label = "Mtrol 4" if is_mt4 else "Mtrol 3"
        lookup = MT4_CONFIG if is_mt4 else MT3_CONFIG
        
        st.sidebar.divider()
        st.sidebar.header(f"🎯 Step 2: {dev_label} Parameters")
        
        # Extract available parameters from columns
        options = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if options:
            selected = st.sidebar.selectbox("Choose curve to plot", options)
            
            # Key mapping for config lookup
            key = "p1" if "p1" in selected.lower() else \
                  "p2" if "p2" in selected.lower() else \
                  "flow" if "flow" in selected.lower() else "opening"
            
            std = lookup[key]

            # Summary Stats
            p_min, p_max = df[selected].min(), df[selected].max()
            t_min, t_max = df['Temp'].min(), df['Temp'].max()
            drift = p_max - p_min
            calc_ppm = (drift * 1000000) / (TEMP_DELTA_FIXED * std["ref"])

            # --- PLOTTING ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Primary Trace: Selected Parameter
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df[selected], 
                name=f"{selected}", line=dict(color="#00CCFF", width=1.5)
            ), secondary_y=False)

            # Secondary Trace: Temperature
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df['Temp'], 
                name="Chamber Temp", line=dict(color="#FFD700", dash='dot', width=2)
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=650,
                hovermode="x unified",
                xaxis=dict(title="Timeline (Mar 11-13)", rangeslider=dict(visible=True)),
                yaxis=dict(
                    title=f"<b>{selected} ({std['unit']})</b>",
                    color="#00CCFF", range=std["range"], dtick=std["dtick"], fixedrange=True
                ),
                yaxis2=dict(
                    title="<b>Chamber Temp (°C)</b>",
                    color="#FFD700", range=TEMP_WINDOW, dtick=10, side='right', fixedrange=True
                ),
                legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center")
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- DATA SUMMARY TABLE ---
            st.divider()
            st.subheader("📋 Statistical Analysis Table")
            
            summary_table = {
                "Metric": ["Min Value", "Max Value", "Total Delta (Max-Min)", "Calculated PPM", "Standard Target PPM"],
                f"Selected: {selected}": [
                    f"{p_min:.4f} {std['unit']}", 
                    f"{p_max:.4f} {std['unit']}", 
                    f"{drift:.4f}", 
                    f"**{calc_ppm:.2f}**", 
                    f"{std['target_ppm']}"
                ],
                "Chamber Temperature": [
                    f"{t_min:.2f} °C", 
                    f"{t_max:.2f} °C", 
                    f"{(t_max - t_min):.2f} °C", 
                    "N/A", 
                    "Reference ΔT: 89.85"
                ]
            }
            
            st.table(pd.DataFrame(summary_table))

    except Exception as e:
        st.error(f"Error during dataset processing: {e}")
else:
    st.info("👋 Upload your Device and Chamber CSVs to plot the analysis curves.")
