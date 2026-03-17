import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. Page Config
st.set_page_config(page_title="Mtrol Precision Analytics", layout="wide")

# --- CUSTOM CSS FOR MOUSE CURSOR & BOXES ---
st.markdown("""
    <style>
    /* Force standard arrow pointer cursor on plot and all sub-elements */
    .js-plotly-plot .plotly .cursor-crosshair,
    .js-plotly-plot .plotly .cursor-pointer,
    .js-plotly-plot .plotly .nsewdrag,
    .js-plotly-plot .plotly .drag,
    .plot-container {
        cursor: default !important;
    }

    /* Metric Box Styling */
    .metric-container {
        text-align: center;
        padding: 15px 10px;
        background-color: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #333;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label {
        font-size: 18px !important; 
        font-weight: 700;
        color: #FFD700;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 16px !important;
        font-weight: 400;
        color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURATION ---
MT3_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [0, 340], "ref": 200.0, "max": 303.5447, "min": 0.0, "ppm": "—"},
    "opening": {"unit": "%", "range": [0, 22], "ref": 100.0, "max": 22.0132, "min": 0.0, "ppm": "308.42"},
    "p1": {"unit": "bar", "range": [0, 12], "ref": 17.0, "max": 10.6029, "min": 0.0, "ppm": "19362.57"},
    "p2": {"unit": "bar", "range": [0, 12], "ref": 17.0, "max": 10.0592, "min": 0.0, "ppm": "9010.37"}
}

MT4_CONFIG = {
    "flow": {"unit": "Kg/Hr", "range": [0, 300], "ref": 500.0, "max": 275.1067, "min": 0.0, "ppm": "—"},
    "opening": {"unit": "%", "range": [0, 22], "ref": 100.0, "max": 19.5011, "min": 0.0, "ppm": "231.453"},
    "p1": {"unit": "bar", "range": [4, 6], "ref": 17.0, "max": 5.3704, "min": 5.3062, "ppm": "129.91"},
    "p2": {"unit": "bar", "range": [9, 11], "ref": 17.0, "max": 10.7396, "min": 10.5863, "ppm": "310.21"}
}

TEMP_WINDOW_ZOOMED = [-30, 80]
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

            # --- METRICS ROW ---
            cols = st.columns(5)
            t_min_obs, t_max_obs = df_full['Temp'].min(), df_full['Temp'].max()
            metrics_data = [(f"Min {selected}", f"{std['min']:.4f}"), (f"Max {selected}", f"{std['max']:.4f}"),
                            ("Min Temp", f"{t_min_obs:.1f} °C" if pd.notnull(t_min_obs) else "—"),
                            ("Max Temp", f"{t_max_obs:.1f} °C" if pd.notnull(t_max_obs) else "—"),
                            (f"{selected} PPM", std["ppm"])]

            for i, (label, val) in enumerate(metrics_data):
                with cols[i]:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">{label}</div><div class="metric-value">{val}</div></div>', unsafe_allow_html=True)

            # --- LAG PREVENTION: DECIMATION ---
            step = 1 if len(df_full) < 50000 else 2
            df_plot = df_full.iloc[::step]

            # --- PLOTTING (POINT CURSOR) ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Param markers (1s)
            fig.add_trace(go.Scattergl(
                x=df_plot['Full_Time'], y=df_plot[selected], mode='markers', 
                marker=dict(size=3, color="#00CCFF", opacity=0.4),
                name=f"{selected}",
                hovertemplate="Time: %{x}<br>Value: %{y:.4f}<extra></extra>"
            ), secondary_y=False)

            # Actual Temp Readings (Yellow Circles)
            temp_points = df_full.dropna(subset=['Temp'])
            fig.add_trace(go.Scattergl(
                x=temp_points['Full_Time'], y=temp_points['Temp'], mode='markers',
                marker=dict(size=6, color="#FFD700", symbol='circle'),
                name="Temp",
                hovertemplate="Time: %{x}<br>Temp: %{y:.2f}°C<extra></extra>"
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=650,
                dragmode=False, 
                # --- MODIFIED: POINT-SPECIFIC CURSOR ---
                hovermode="closest", 
                hoverdistance=50, # Sensitivity of "catching" a point
                xaxis=dict(
                    title="<b>Time Stamp</b>",
                    rangeslider=dict(visible=True, thickness=0.06),
                    fixedrange=False,
                    showspikes=False # Removed spikes for clean point cursor
                ),
                yaxis=dict(title=f"<b>{selected}</b>", range=std["range"], color="#00CCFF", fixedrange=True),
                yaxis2=dict(title="<b>Temp (°C)</b>", range=TEMP_WINDOW_ZOOMED, side='right', color="#FFD700", fixedrange=True),
                margin=dict(t=30, b=10),
                legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
                hoverlabel=dict(bgcolor="#1e1e1e", font_size=13, font_family="Arial")
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            # --- TABLE ---
            st.divider()
            st.subheader("📄 Original Synced Dataset")
            st.dataframe(df_full.fillna("—"), use_container_width=True, height=400)
            
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload CSV files to begin.")
