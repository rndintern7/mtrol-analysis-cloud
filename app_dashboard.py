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
# Mtrol 3 Specifics
MT3_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "dtick": 20, "ref": 200.0, "target_ppm": "N/A"},
    "opening": {"unit": "%", "range": [-20, 70], "dtick": 10, "ref": 100.0, "target_ppm": 2449.99},
    "p1": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 21455.76},
    "p2": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 20355.54}
}

# Mtrol 4 Specifics
MT4_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [200, 320], "dtick": 20, "ref": 500.0, "target_ppm": "N/A"},
    "opening": {"unit": "%", "range": [-20, 70], "dtick": 10, "ref": 100.0, "target_ppm": 2170.41},
    "p1": {"unit": "bar", "range": [4, 6], "dtick": 0.5, "ref": 17.0, "target_ppm": 129.91}, # Special P1 range
    "p2": {"unit": "bar", "range": [0, 12], "dtick": 2, "ref": 17.0, "target_ppm": 310.21}
}

TEMP_WINDOW = [-20, 70] # Fixed Temperature Y-Axis
TEMP_DELTA_FIXED = 89.85
START_TIME = "2026-03-11 10:20:00"
END_TIME = "2026-03-13 11:30:00"

@st.cache_data
def load_and_sync(dev_file, temp_file):
    # Load Chamber Temp
    df_t = pd.read_csv(temp_file).dropna(how='all')
    df_t.columns = ['Timestamp', 'Temp']
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # Load Device Data
    df_d = pd.read_csv(dev_file)
    time_col = next((c for c in df_d.columns if "time" in c.lower()), "Time Stamp")
    df_d[time_col] = pd.to_datetime(df_d[time_col], errors='coerce')
    
    # Clean numeric data (removes ** or non-numeric text)
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_d.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(time_col).mean().sort_index()
    combined = pd.concat([df_d, df_t], axis=1)
    combined['Temp'] = combined['Temp'].interpolate(method='time')
    
    # Apply Time Window
    combined = combined.loc[START_TIME : END_TIME].reset_index().rename(columns={'index': 'Full_Time'})
    
    # Performance Downsampling
    if len(combined) > 40000:
        step = len(combined) // 40000
        combined = combined.iloc[::step]
        
    return combined

# --- MAIN INTERFACE ---
st.title("Mtrol Precision Analytics - Cloud Dashboard")

st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber CSV", type=['csv'])

if dev_upload and temp_upload:
    try:
        df = load_and_sync(dev_upload, temp_upload)
        
        # Auto-detect Mtrol version from filename
        is_mt4 = "MT4" in dev_upload.name.upper()
        dev_label = "Mtrol 4" if is_mt4 else "Mtrol 3"
        lookup = MT4_CONFIG if is_mt4 else MT3_CONFIG
        
        st.sidebar.divider()
        st.sidebar.header(f"🎯 Step 2: {dev_label} Parameters")
        options = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if options:
            selected = st.sidebar.selectbox("Choose curve to analyze", options)
            # Map column name to logic key
            key = "p1" if "p1" in selected.lower() else \
                  "p2" if "p2" in selected.lower() else \
                  "flow" if "flow" in selected.lower() else "opening"
            
            std = lookup[key]

            # Calculation Summary
            p_min, p_max = df[selected].min(), df[selected].max()
            t_min, t_max = df['Temp'].min(), df['Temp'].max()
            drift = p_max - p_min
            calc_ppm = (drift * 1000000) / (TEMP_DELTA_FIXED * std["ref"])

            # --- GRAPHING SECTION ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Left Axis: Parameter
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df[selected], 
                name=f"{selected} (Device)", line=dict(color="#00CCFF", width=1.5)
            ), secondary_y=False)

            # Right Axis: Temperature
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

            # --- MIN/MAX & PPM SUMMARY TABLE ---
            st.divider()
            st.subheader("📋 Stability Summary & Min/Max Analysis")
            
            summary_table = {
                "Metric": ["Min Value Recorded", "Max Value Recorded", "Total Drift (Max-Min)", "Calculated PPM", "Standard Target PPM"],
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
                    "Target ΔT: 89.85"
                ]
            }
            
            st.table(pd.DataFrame(summary_table))
            
            # Mathematical Verification
            with st.expander("🔍 View Calculation Logic"):
                st.latex(rf"PPM = \frac{{{drift:.4f} \times 1,000,000}}{{89.85 \times {std['ref']}}}")
        else:
            st.error("Matching parameters (P1, P2, Flow, Opening) not found in CSV.")

    except Exception as e:
        st.error(f"Critical Error: {e}")
else:
    st.info("Please upload your Device and Chamber data files to begin.")
