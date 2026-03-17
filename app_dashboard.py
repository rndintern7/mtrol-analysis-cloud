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

# --- STANDARDS & SCALING ---
MT3_VALS = {
    "flow": {"ref_range": 200.0, "unit": "Kg/Hr", "range": [0.0, 320.0]},
    "opening": {"ref_range": 100.0, "unit": "%", "range": [-10.0, 110.0]},
    "p1": {"ref_range": 17.0, "unit": "bar", "range": [0.0, 20.0]},
    "p2": {"ref_range": 17.0, "unit": "bar", "range": [0.0, 20.0]}
}

MT4_VALS = {
    "flow": {"ref_range": 500.0, "unit": "Kg/Hr", "range": [0.0, 550.0]},
    "opening": {"ref_range": 100.0, "unit": "%", "range": [-10.0, 110.0]},
    "p1": {"ref_range": 17.0, "unit": "bar", "range": [0.0, 20.0]},
    "p2": {"ref_range": 17.0, "unit": "bar", "range": [0.0, 20.0]}
}

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
    
    if len(combined) > 30000:
        step = len(combined) // 30000
        combined = combined.iloc[::step]
        
    return combined

# --- UI LAYOUT ---
st.title("Mtrol Analysis Cloud Dashboard")

st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber CSV", type=['csv'])

if dev_upload and temp_upload:
    try:
        df = load_and_sync(dev_upload, temp_upload)
        dev_type = "Mtrol 4" if "MT4" in dev_upload.name.upper() else "Mtrol 3"
        lookup = MT4_VALS if dev_type == "Mtrol 4" else MT3_VALS
        
        options = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if options:
            selected = st.sidebar.selectbox("Choose data for sync view", options)
            key = next((k for k in ["flow", "opening", "p1", "p2"] if k in selected.lower()), "p1")
            std = lookup[key]

            # --- Y-AXIS SLIDER SIMULATION ---
            st.sidebar.divider()
            st.sidebar.header("↕️ Step 3: Y-Axis Zoom Control")
            y_min = st.sidebar.number_input(f"Y-Axis Min ({std['unit']})", value=float(std["range"][0]))
            y_max = st.sidebar.number_input(f"Y-Axis Max ({std['unit']})", value=float(std["range"][1]))

            # Main Graph
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df[selected], name=selected, line=dict(color="#00CCFF")), secondary_y=False)
            fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df['Temp'], name="Temp", line=dict(color="#FFD700", dash='dot')), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=700,
                hovermode="x unified",
                xaxis=dict(
                    title="Timeline", 
                    rangeslider=dict(visible=True, thickness=0.08)
                ),
                yaxis=dict(
                    title=f"<b>{selected} ({std['unit']})</b>",
                    range=[y_min, y_max], # CONTROLLED BY SIDEBAR "SLIDER"
                    fixedrange=False,
                    color="#00CCFF"
                ),
                yaxis2=dict(
                    title="<b>Temp (°C)</b>",
                    side='right',
                    range=[-20, 70],
                    color="#FFD700"
                )
            )

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
            st.info(f"💡 Adjust the **Y-Axis Min/Max** in the sidebar to zoom vertically.")

    except Exception as e:
        st.error(f"Processing error: {e}")
else:
    st.info("Waiting for CSV files...")
