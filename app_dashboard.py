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
    # Targets specific headers: 'Time Stamp' and 'Chamber Temperature (°C)'
    df_t = pd.read_csv(temp_file).dropna(how='all')
    t_time_col = 'Time Stamp' if 'Time Stamp' in df_t.columns else df_t.columns[0]
    t_val_col = 'Chamber Temperature (°C)' if 'Chamber Temperature (°C)' in df_t.columns else df_t.columns[1]
    
    df_t = df_t[[t_time_col, t_val_col]].rename(columns={t_time_col: 'Timestamp', t_val_col: 'Temp'})
    df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'], errors='coerce')
    df_t = df_t.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # --- 2. Process Device Data ---
    df_d = pd.read_csv(dev_file)
    # Flexible time column detection
    d_time_col = next((c for c in df_d.columns if "time" in c.lower() or "date" in c.lower()), df_d.columns[0])
    df_d[d_time_col] = pd.to_datetime(df_d[d_time_col], errors='coerce')
    
    # Clean numeric data (remove units/symbols if present)
    for col in df_d.columns:
        if col != d_time_col:
            df_d[col] = pd.to_numeric(df_d[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    df_d = df_d.groupby(d_time_col).mean().sort_index()

    # --- 3. Synchronize ---
    combined = pd.concat([df_d, df_t], axis=1)
    # Clip to device data duration
    combined = combined.loc[df_d.index.min() : df_d.index.max()].reset_index().rename(columns={'index': 'Full_Time'})
    return combined

# --- SIDEBAR CONTROLS ---
st.sidebar.header("📁 Step 1: Data Upload")
dev_upload = st.sidebar.file_uploader("Upload Device CSV", type=['csv'])
temp_upload = st.sidebar.file_uploader("Upload Chamber_Temp.csv", type=['csv'])
std_upload = st.sidebar.file_uploader("Upload Standard_Limits.csv", type=['csv'])

if dev_upload and temp_upload and std_upload:
    try:
        df_full = load_and_sync(dev_upload, temp_upload)
        df_std = pd.read_csv(std_upload)
        
        # Identify numeric device parameters
        excluded = ['Full_Time', 'Temp', 'Timestamp', 'Unnamed']
        param_options = [c for c in df_full.columns if not any(x in c for x in excluded)]
        
        if param_options:
            selected_param = st.sidebar.selectbox("Choose Parameter to Analyze", param_options)
            
            # --- PPM COMPONENTS ---
            # 1. Device Range (Current selection)
            d_max, d_min = df_full[selected_param].max(), df_full[selected_param].min()
            device_range = d_max - d_min

            # 2. Temperature Range (Chamber)
            t_max, t_min = df_full['Temp'].max(), df_full['Temp'].min()
            temp_range = t_max - t_min

            # 3. Standard Range (Lookup from Standard_Limits file)
            # We match using the first word (e.g., "P1" in device matches "P1 (bar)" in standard)
            match_key = re.escape(selected_param.split(' ')[0])
            std_row = df_std[df_std['Parameters'].str.contains(match_key, case=False, na=False)]
            
            if not std_row.empty:
                s_max = std_row.iloc[0]['Maximum Value']
                s_min = std_row.iloc[0]['Minimum Value']
                standard_range = s_max - s_min
                std_found = True
            else:
                s_max, s_min, standard_range = "N/A", "N/A", 0
                std_found = False

            # --- FINAL PPM CALCULATION ---
            # Formula: ([Device Range] * 10^6) / ([Temp Range] * [Standard Range])
            denom = temp_range * standard_range
            ppm_final = (device_range * 1_000_000) / denom if denom != 0 else 0

            # --- METRICS DASHBOARD ---
            st.subheader(f"Analysis for {selected_param}")
            cols = st.columns(5)
            
            m_data = [
                ("Device Range", f"Min: {d_min:.4f}<br>Max: {d_max:.4f}"),
                ("Temp Range", f"Min: {t_min:.2f}°C<br>Max: {t_max:.2f}°C"),
                ("Standard Range", f"Min: {s_min}<br>Max: {s_max}"),
                ("Matched Parameter", std_row.iloc[0]['Parameters'] if std_found else "None"),
                ("Calculated PPM", f"<div class='ppm-value'>{ppm_final:.2f}</div>")
            ]

            for i, (label, value) in enumerate(m_data):
                with cols[i]:
                    st.markdown(f'<div class="metric-container"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

            # --- INTERACTIVE GRAPH ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Primary: Device Parameter
            fig.add_trace(go.Scattergl(
                x=df_full['Full_Time'], y=df_full[selected_param], 
                name=selected_param, line=dict(color="#00CCFF", width=2)
            ), secondary_y=False)

            # Secondary: Chamber Temperature
            fig.add_trace(go.Scattergl(
                x=df_full['Full_Time'], y=df_full['Temp'], 
                name="Chamber Temp", line=dict(color="#FFD700", width=1.5, dash='dot')
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600,
                xaxis=dict(title="Time Stamp", rangeslider=dict(visible=True, thickness=0.05)),
                yaxis=dict(title=f"<b>{selected_param}</b>", color="#00CCFF"),
                yaxis2=dict(title="<b>Temp (°C)</b>", side="right", color="#FFD700"),
                legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center")
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            if not std_found:
                st.warning(f"Note: '{selected_param}' not found in the Standard Limits CSV. PPM cannot be calculated correctly.")

    except Exception as e:
        st.error(f"Analysis Error: {e}")
else:
    st.info("👋 Ready. Please upload all 3 files to calculate PPM and generate graphs.")
