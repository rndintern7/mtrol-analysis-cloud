import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

# 1. Page Config
st.set_page_config(page_title="Universal Precision Analytics", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .metric-container {
        text-align: center;
        padding: 15px 10px;
        background-color: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #333;
        min-height: 110px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label { font-size: 14px !important; font-weight: 700; color: #FFD700; margin-bottom: 5px; }
    .metric-value { font-size: 15px !important; font-weight: 400; color: #ffffff; line-height: 1.4; }
    .ppm-value { font-size: 24px !important; font-weight: 800; color: #00FF00; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_and_sync(dev_file, temp_file):
    # --- 1. Process Chamber Temp Data ---
    df_t = pd.read_csv(temp_file).dropna(how='all')
    # Target confirmed headers: 'Time Stamp' and 'Chamber Temperature (°C)'
    t_time_col = 'Time Stamp' if 'Time Stamp' in df_t.columns else df_t.columns[0]
    t_val_col = 'Chamber Temperature (°C)' if 'Chamber Temperature (°C)' in df_t.columns else df_t.columns[1]
    
    df_t = df_t[[t_time_col, t_val_col]].rename(columns={t_time_col: 'Timestamp', t_val_col: 'Temp'})
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # --- 2. Process Device Data ---
    df_d = pd.read_csv(dev_file)
    d_time_col = 'Time Stamp' if 'Time Stamp' in df_d.columns else df_d.columns[0]
    df_d[d_time_col] = pd.to_datetime(df_d[d_time_col], errors='coerce')
    
    # Clean numeric data
    for col in df_d.columns:
        if col != d_time_col:
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(d_time_col).mean().sort_index()

    # --- 3. Synchronize ---
    combined = pd.concat([df_d, df_t], axis=1)
    combined = combined.loc[df_d.index.min() : df_d.index.max()].reset_index().rename(columns={'index': 'Full_Time'})
    return combined

# --- SIDEBAR ---
st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV (MT3/MT4/MUPT)", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber_Temp.csv", type=['csv'])
std_upload = st.sidebar.file_uploader("Upload Standard_Limits_MTrol.csv", type=['csv'])

if dev_upload and temp_upload and std_upload:
    try:
        df_full = load_and_sync(dev_upload, temp_upload)
        df_std = pd.read_csv(std_upload)
        
        excluded = ['Full_Time', 'Temp', 'Timestamp', 'Unnamed']
        param_options = [c for c in df_full.columns if not any(x in c for x in excluded)]
        
        if param_options:
            selected_param = st.sidebar.selectbox("Select Parameter", param_options)
            
            # --- PPM COMPONENTS ---
            d_max, d_min = df_full[selected_param].max(), df_full[selected_param].min()
            t_max, t_min = df_full['Temp'].max(), df_full['Temp'].min()
            
            # Standard Lookup
            match_key = re.escape(selected_param.split(' ')[0])
            std_row = df_std[df_std['Parameters'].str.contains(match_key, case=False, na=False)]
            
            if not std_row.empty:
                s_max, s_min = std_row.iloc[0]['Maximum Value'], std_row.iloc[0]['Minimum Value']
                std_range = s_max - s_min
                # Formula: ([Device Range] * 10^6) / ([Temp Range] * [Standard Range])
                ppm = ((d_max - d_min) * 1_000_000) / ((t_max - t_min) * std_range) if (t_max-t_min)*std_range != 0 else 0
                std_name = std_row.iloc[0]['Parameters']
            else:
                ppm, s_max, s_min, std_name = 0, "N/A", "N/A", "Not Found"

            # --- METRICS ---
            st.subheader(f"Results: {selected_param}")
            cols = st.columns(5)
            m_data = [
                ("Device Range", f"Min: {d_min:.4f}<br>Max: {d_max:.4f}"),
                ("Temp Range", f"Min: {t_min:.2f}°C<br>Max: {t_max:.2f}°C"),
                ("Standard Range", f"Min: {s_min}<br>Max: {s_max}"),
                ("Matched Standard", std_name),
                ("Calculated PPM", f"<div class='ppm-value'>{ppm:.2f}</div>")
            ]
            for i, (l, v) in enumerate(m_data):
                with cols[i]:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">{l}</div><div class="metric-value">{v}</div></div>', unsafe_allow_html=True)

            # --- SCATTER PLOT ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Trace 1: Parameter (Blue Circles)
            fig.add_trace(go.Scattergl(
                x=df_full['Full_Time'], 
                y=df_full[selected_param], 
                mode='markers',
                name=selected_param,
                marker=dict(color='#007BFF', size=5, opacity=0.7, symbol='circle')
            ), secondary_y=False)

            # Trace 2: Chamber Temp (Yellow Circles)
            fig.add_trace(go.Scattergl(
                x=df_full['Full_Time'], 
                y=df_full['Temp'], 
                mode='markers',
                name="Chamber Temperature",
                marker=dict(color='#FFD700', size=5, opacity=0.7, symbol='circle')
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600,
                xaxis=dict(title="Time Stamp", rangeslider=dict(visible=True, thickness=0.04)),
                yaxis=dict(title=f"<b>{selected_param}</b>", color="#007BFF"),
                yaxis2=dict(title="<b>Temp (°C)</b>", side="right", color="#FFD700"),
                legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center")
            )
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload the Device Data, Chamber_Temp.csv, and Standard_Limits_MTrol.csv.")
