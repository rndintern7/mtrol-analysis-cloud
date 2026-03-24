import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

# 1. Page Configuration
st.set_page_config(page_title="Universal Precision Analytical Dashboard", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .metric-container {
        text-align: center;
        padding: 15px 5px;
        background-color: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #444;
        min-height: 110px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label { font-size: 12px !important; font-weight: 700; color: #FFD700; margin-bottom: 5px; text-transform: uppercase; }
    .metric-value { font-size: 14px !important; color: #ffffff; line-height: 1.3; }
    .ppm-value { font-size: 26px !important; font-weight: 800; color: #ffffff !important; }
    .main-title { 
        font-size: 36px; 
        font-weight: 800; 
        color: #ffffff; 
        margin-bottom: 25px; 
        border-left: 5px solid #87CEEB; 
        padding-left: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_and_process(dev_file, temp_file):
    # 1. Process Chamber Temp
    df_t = pd.read_csv(temp_file).dropna(how='all')
    t_time_col = 'Time Stamp' if 'Time Stamp' in df_t.columns else df_t.columns[0]
    t_val_col = 'Chamber Temperature (°C)' if 'Chamber Temperature (°C)' in df_t.columns else df_t.columns[1]
    df_t = df_t[[t_time_col, t_val_col]].rename(columns={t_time_col: 'Timestamp', t_val_col: 'Temp'})
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # 2. Process Device Data
    df_d = pd.read_csv(dev_file)
    d_time_col = 'Time Stamp' if 'Time Stamp' in df_d.columns else df_d.columns[0]
    df_d[d_time_col] = pd.to_datetime(df_d[d_time_col], errors='coerce')
    
    for col in df_d.columns:
        if col != d_time_col:
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    raw_stats = {}
    for col in df_d.columns:
        if col != d_time_col:
            raw_stats[col] = {'max': df_d[col].max(), 'min': df_d[col].min()}

    # 3. Synchronize & Fill
    df_d_sync = df_d.groupby(d_time_col).mean().sort_index()
    combined = pd.concat([df_d_sync, df_t], axis=1)
    combined['Temp'] = combined['Temp'].ffill().bfill()
    combined = combined.loc[df_d_sync.index.min() : df_d_sync.index.max()].reset_index().rename(columns={'index': 'Full_Time'})
    
    # Performance Downsampling (40,000 points)
    plot_data = combined.copy()
    if len(plot_data) > 40000:
        factor = len(plot_data) // 40000
        plot_data = plot_data.iloc[::factor].reset_index(drop=True)
    
    return plot_data, raw_stats

# --- SIDEBAR ---
st.sidebar.header("📁 Data Sources")
dev_upload = st.sidebar.file_uploader("1. Device Data", type=['csv'])
temp_upload = st.sidebar.file_uploader("2. Chamber Temp", type=['csv'])
std_upload = st.sidebar.file_uploader("3. Standard Limits", type=['csv'])

if dev_upload and temp_upload and std_upload:
    try:
        df_plot, device_raw_stats = load_and_process(dev_upload, temp_upload)
        df_std = pd.read_csv(std_upload)
        
        excluded = ['Full_Time', 'Temp', 'Timestamp', 'Unnamed']
        param_options = [c for c in df_plot.columns if not any(x in c for x in excluded)]
        
        if param_options:
            selected_param = st.sidebar.selectbox("Analysis Parameter", param_options)
            
            # --- Y-AXIS LIMITS ---
            fname = dev_upload.name.upper()
            y_range = None
            if "MT4" in fname:
                ranges = {"FLOW": [0, 310], "OPEN": [0, 25], "P1": [0, 10], "P2": [0, 15]}
                for k, v in ranges.items():
                    if k in selected_param.upper(): y_range = v
            elif "MT3" in fname:
                ranges = {"FLOW": [0, 320], "OPEN": [0, 25], "P1": [0, 15], "P2": [0, 15]}
                for k, v in ranges.items():
                    if k in selected_param.upper(): y_range = v

            # --- CALCULATIONS ---
            d_max, d_min = device_raw_stats[selected_param]['max'], device_raw_stats[selected_param]['min']
            t_max, t_min = df_plot['Temp'].max(), df_plot['Temp'].min()
            
            match_key = re.escape(selected_param.split(' ')[0])
            std_row = df_std[df_std['Parameters'].str.contains(match_key, case=False, na=False)]
            
            if not std_row.empty:
                s_max, s_min = std_row.iloc[0]['Maximum Value'], std_row.iloc[0]['Minimum Value']
                std_range = s_max - s_min
                ppm = ((d_max - d_min) * 1_000_000) / ((t_max - t_min) * std_range) if (t_max-t_min)*std_range != 0 else 0
                
                # Flow Rate Dash Logic
                if "FLOW" in selected_param.upper() and round(ppm, 2) == 0:
                    ppm_display = "-"
                else:
                    ppm_display = f"{ppm:.2f}"
            else:
                s_max, s_min, ppm_display = "N/A", "N/A", "-"

            # --- UPDATED HEADER ---
            st.markdown('<div class="main-title">Universal Precision Analytical Dashboard</div>', unsafe_allow_html=True)
            
            # --- DASHBOARD METRICS ---
            cols = st.columns(4)
            m_data = [
                (f"{selected_param} Range", f"Min: {d_min:.4f}<br>Max: {d_max:.4f}"),
                ("Temp Range", f"Min: {t_min:.2f}°C<br>Max: {t_max:.2f}°C"),
                ("Standard Range", f"Min: {s_min}<br>Max: {s_max}"),
                ("PPM Value", f"<div class='ppm-value'>{ppm_display}</div>")
            ]
            for i, (label, val) in enumerate(m_data):
                with cols[i]:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">{label}</div><div class="metric-value">{val}</div></div>', unsafe_allow_html=True)

            # --- DOTTED SCATTER PLOT ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Sky Blue Markers for Selected Parameter
            fig.add_trace(go.Scattergl(
                x=df_plot['Full_Time'], y=df_plot[selected_param], 
                mode='markers', name=selected_param,
                marker=dict(color='skyblue', size=4, symbol='circle', opacity=0.8),
                hovertemplate="Val: %{y:.4f}<extra></extra>"
            ), secondary_y=False)

            # Yellow Markers for Chamber Temp
            fig.add_trace(go.Scattergl(
                x=df_plot['Full_Time'], y=df_plot['Temp'], 
                mode='markers', name="Chamber Temp",
                marker=dict(color='#FFD700', size=4, symbol='circle', opacity=0.8),
                hovertemplate="Temp: %{y:.2f}°C<extra></extra>"
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=650,
                hovermode='x unified',
                xaxis=dict(
                    title="Time Stamp", 
                    showspikes=True, 
                    spikemode='marker+across', # Snap-to-dot cursor
                    spikesnap='data',
                    spikecolor="#ffffff",
                    spikethickness=1,
                    rangeslider=dict(visible=True, thickness=0.04)
                ),
                yaxis=dict(title=f"<b>{selected_param}</b>", color="skyblue", range=y_range, fixedrange=False),
                yaxis2=dict(title="<b>Temp (°C)</b>", side="right", color="#FFD700", range=[-20, 80], fixedrange=False),
                legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
                dragmode='zoom'
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False})

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload your data files to initialize the Analytical Dashboard.")
