import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

# 1. Page Configuration
st.set_page_config(page_title="Universal Precision Analytics", layout="wide")

# --- CUSTOM CSS FOR 4-COLUMN NEAT LAYOUT ---
st.markdown("""
    <style>
    .metric-container {
        text-align: center;
        padding: 20px 10px;
        background-color: #1e1e1e;
        border-radius: 12px;
        border: 1px solid #444;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label { 
        font-size: 13px !important; 
        font-weight: 700; 
        color: #FFD700; 
        margin-bottom: 8px; 
        text-transform: uppercase;
    }
    .metric-value { 
        font-size: 15px !important; 
        font-weight: 400; 
        color: #ffffff; 
        line-height: 1.5; 
    }
    .ppm-value { 
        font-size: 28px !important; 
        font-weight: 800; 
        color: #ffffff !important; 
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_and_process(dev_file, temp_file):
    # Process Chamber Temp Data
    df_t = pd.read_csv(temp_file).dropna(how='all')
    t_time_col = 'Time Stamp' if 'Time Stamp' in df_t.columns else df_t.columns[0]
    t_val_col = 'Chamber Temperature (°C)' if 'Chamber Temperature (°C)' in df_t.columns else df_t.columns[1]
    
    df_t = df_t[[t_time_col, t_val_col]].rename(columns={t_time_col: 'Timestamp', t_val_col: 'Temp'})
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t_sync = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # Process Device Data
    df_d = pd.read_csv(dev_file)
    d_time_col = 'Time Stamp' if 'Time Stamp' in df_d.columns else df_d.columns[0]
    df_d[d_time_col] = pd.to_datetime(df_d[d_time_col], errors='coerce')
    
    for col in df_d.columns:
        if col != d_time_col:
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    # Capture Absolute Peak Values BEFORE syncing
    raw_stats = {}
    for col in df_d.columns:
        if col != d_time_col:
            raw_stats[col] = {'max': df_d[col].max(), 'min': df_d[col].min()}

    # Synchronize for plotting
    df_d_sync = df_d.groupby(d_time_col).mean().sort_index()
    combined = pd.concat([df_d_sync, df_t_sync], axis=1)
    combined = combined.loc[df_d_sync.index.min() : df_d_sync.index.max()].reset_index().rename(columns={'index': 'Full_Time'})
    
    return combined, raw_stats

# --- SIDEBAR ---
st.sidebar.header("📁 Step 1: Upload Files")
dev_upload = st.sidebar.file_uploader("1. Device Data (MT3/MT4)", type=['csv'])
temp_upload = st.sidebar.file_uploader("2. Chamber_Temp.csv", type=['csv'])
std_upload = st.sidebar.file_uploader("3. Standard_Limits_MTrol.csv", type=['csv'])

if dev_upload and temp_upload and std_upload:
    try:
        df_plot, device_raw_stats = load_and_process(dev_upload, temp_upload)
        df_std = pd.read_csv(std_upload)
        
        excluded = ['Full_Time', 'Temp', 'Timestamp', 'Unnamed']
        param_options = [c for c in df_plot.columns if not any(x in c for x in excluded)]
        
        if param_options:
            selected_param = st.sidebar.selectbox("Select Parameter", param_options)
            
            # --- Y-AXIS RANGES ---
            fname = dev_upload.name.upper()
            y_range = None
            if "MT4" in fname:
                ranges = {"FLOW": [0, 300], "OPEN": [0, 22], "P1": [0, 6], "P2": [0, 12]}
                for k, v in ranges.items():
                    if k in selected_param.upper(): y_range = v
            elif "MT3" in fname:
                ranges = {"FLOW": [0, 320], "OPEN": [0, 24], "P1": [0, 12], "P2": [0, 12]}
                for k, v in ranges.items():
                    if k in selected_param.upper(): y_range = v

            # --- CALCULATIONS ---
            d_max = device_raw_stats[selected_param]['max']
            d_min = device_raw_stats[selected_param]['min']
            t_max, t_min = df_plot['Temp'].max(), df_plot['Temp'].min()
            
            match_key = re.escape(selected_param.split(' ')[0])
            std_row = df_std[df_std['Parameters'].str.contains(match_key, case=False, na=False)]
            
            if not std_row.empty:
                s_max, s_min = std_row.iloc[0]['Maximum Value'], std_row.iloc[0]['Minimum Value']
                std_range = s_max - s_min
                ppm = ((d_max - d_min) * 1_000_000) / ((t_max - t_min) * std_range) if (t_max-t_min)*std_range != 0 else 0
            else:
                s_max, s_min, ppm = "N/A", "N/A", 0

            # --- 4 NEAT METRIC BOXES ---
            st.subheader(f"Analysis Dashboard: {selected_param}")
            cols = st.columns(4)
            m_data = [
                (f"{selected_param} Range", f"Min: {d_min:.4f}<br>Max: {d_max:.4f}"),
                ("Chamber Temp Range", f"Min: {t_min:.2f}°C<br>Max: {t_max:.2f}°C"),
                (f"{selected_param} Standard Range", f"Min: {s_min}<br>Max: {s_max}"),
                (f"{selected_param} PPM", f"<div class='ppm-value'>{ppm:.2f}</div>")
            ]
            for i, (label, val) in enumerate(m_data):
                with cols[i]:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">{label}</div><div class="metric-value">{val}</div></div>', unsafe_allow_html=True)

            # --- PLOT WITH DOT CURSOR & UNIFIED HOVER ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Trace 1: Parameter (Blue Markers)
            fig.add_trace(go.Scattergl(
                x=df_plot['Full_Time'], y=df_plot[selected_param], 
                mode='markers', name=selected_param,
                marker=dict(color='#007BFF', size=6, opacity=0.8),
                hovertemplate="%{y:.4f}<extra></extra>" 
            ), secondary_y=False)

            # Trace 2: Temperature (Yellow Markers)
            fig.add_trace(go.Scattergl(
                x=df_plot['Full_Time'], y=df_plot['Temp'], 
                mode='markers', name="Chamber Temp",
                marker=dict(color='#FFD700', size=6, opacity=0.8),
                hovertemplate="%{y:.2f}°C<extra></extra>"
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=680,
                hovermode='x unified', # Shows Time at top + both values in one box
                xaxis=dict(
                    title="Time Stamp", 
                    type='date',
                    showspikes=True, 
                    spikemode='marker+across', # CORRECTED: singular 'marker'
                    spikesnap='cursor',
                    spikethickness=1,
                    spikecolor="#999999",
                    rangeslider=dict(visible=True, thickness=0.04)
                ),
                yaxis=dict(
                    title=f"<b>{selected_param}</b>", 
                    color="#007BFF", 
                    range=y_range, 
                    fixedrange=False 
                ),
                yaxis2=dict(
                    title="<b>Chamber Temp (°C)</b>", 
                    side="right", 
                    color="#FFD700", 
                    range=[-20, 80], 
                    fixedrange=False 
                ),
                legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
                dragmode='zoom', 
                margin=dict(l=20, r=20, t=100, b=20)
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False})

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Awaiting file uploads to generate analysis.")
