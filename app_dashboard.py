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
    "flow": {"ref_range": 200.0, "ppm_target": None, "unit": "Kg/Hr", "range": [0, 320], "dtick": 40},
    "opening": {"ref_range": 100.0, "ppm_target": 2449.99, "unit": "%", "range": [-10, 110], "dtick": 20},
    "p1": {"ref_range": 17.0, "ppm_target": 21455.76, "unit": "bar", "range": [0, 20], "dtick": 2},
    "p2": {"ref_range": 17.0, "ppm_target": 20355.54, "unit": "bar", "range": [0, 20], "dtick": 2}
}

MT4_VALS = {
    "flow": {"ref_range": 500.0, "ppm_target": None, "unit": "Kg/Hr", "range": [0, 550], "dtick": 50},
    "opening": {"ref_range": 100.0, "ppm_target": 2170.41, "unit": "%", "range": [-10, 110], "dtick": 20},
    "p1": {"ref_range": 17.0, "ppm_target": 129.91, "unit": "bar", "range": [0, 20], "dtick": 2},
    "p2": {"ref_range": 17.0, "ppm_target": 310.21, "unit": "bar", "range": [0, 20], "dtick": 2}
}

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
    
    # Clean numeric data (** or text)
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_d.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(time_col).mean().sort_index()

    # Merge and Sync
    combined = pd.concat([df_d, df_t], axis=1)
    combined['Temp'] = combined['Temp'].interpolate(method='time')
    
    # Filter for your specific window
    combined = combined.loc[START_TIME : END_TIME].reset_index().rename(columns={'index': 'Full_Time'})
    
    # Performance Optimization (WebGL)
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
        
        # 1. Standalone Temp Plot
        st.subheader("🌡️ 1. Chamber Temperature Verification")
        temp_fig = go.Figure()
        temp_fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df['Temp'], line=dict(color="#FFD700")))
        temp_fig.update_layout(template="plotly_dark", height=250, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(temp_fig, use_container_width=True)

        # 2. Synchronized Selector
        st.sidebar.divider()
        st.sidebar.header("🎯 Step 2: Select Parameter")
        options = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if options:
            selected = st.sidebar.selectbox("Choose data for sync view", options)
            key = next((k for k in ["flow", "opening", "p1", "p2"] if k in selected.lower()), "p1")
            std = lookup[key]

            # PPM Calculation
            drift = df[selected].max() - df[selected].min()
            final_ppm = (drift * 1000000) / (TEMP_DELTA_FIXED * std["ref_range"])

            st.subheader(f"📊 2. Synchronized Analysis: {selected}")
            
            # Metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Device", dev_type)
            c2.metric("Total Drift", f"{drift:.4f} {std['unit']}")
            c3.metric("PPM Stability", f"{final_ppm:.2f}")
            c4.metric("Time Window", "Mar 11-13")

            # Main Graph
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df[selected], name=selected, line=dict(color="#00CCFF")), secondary_y=False)
            fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df['Temp'], name="Temp", line=dict(color="#FFD700", dash='dot')), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600, hovermode="x unified",
                xaxis=dict(title="Timeline", rangeslider=dict(visible=True)),
                yaxis=dict(title=f"{selected}", range=std["range"], dtick=std["dtick"]),
                yaxis2=dict(title="Temp (°C)", side='right', range=[-20, 70])
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("🔍 Math Detail"):
                st.latex(rf"PPM = \frac{{{drift:.4f} \times 1,000,000}}{{{TEMP_DELTA_FIXED} \times {std['ref_range']}}}")
    except Exception as e:
        st.error(f"Processing error: {e}")
else:
    st.info("Waiting for CSV files...")
