import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64

# 1. Page Config
st.set_page_config(page_title="Advanced Product Analytics", layout="wide")

# --- Function to load local logo ---
def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except: return ""

logo_base64 = get_base64_image("logo.png")

# --- HEADER ---
col_title, col_logo = st.columns([8, 2])
with col_title:
    st.title("Device Analysis System")

with col_logo:
    if logo_base64:
        st.markdown(f'<div style="text-align:right;"><img src="data:image/png;base64,{logo_base64}" style="width:180px;"></div>', unsafe_allow_html=True)

# 2. SIDEBAR CONFIGURATION
st.sidebar.header("📊 Control Panel")
device = st.sidebar.selectbox("Select Product", ["Mtrol 3", "Mtrol 4", "MUPT"])

# Define Parameters for each device
params_map = {
    "Mtrol 3": ["1: Flow Rate", "2: % Opening", "3: P1", "4: P2"],
    "Mtrol 4": ["1: Flow Rate", "2: % Opening", "3: P1", "4: P2"],
    "MUPT": ["C1 Measurement", "C2 Measurement", "T1 Measurement", "T2 Measurement", 
             "Trap Mode", "Bypass Mode", "Solenoid Status", "Steam Leak", 
             "Water Log/Process Off", "Cooling Cycle Switch"]
}

# --- COLOR PALETTE ---
# Specific colors assigned per device and parameter
color_palette = {
    "Mtrol 3": {"1: Flow Rate": "#1f77b4", "2: % Opening": "#2ca02c", "3: P1": "#ff7f0e", "4: P2": "#9467bd"},
    "Mtrol 4": {"1: Flow Rate": "#d62728", "2: % Opening": "#17becf", "3: P1": "#bcbd22", "4: P2": "#e377c2"},
    "MUPT": {
        "C1 Measurement": "#1f77b4", "C2 Measurement": "#ff7f0e", 
        "T1 Measurement": "#2ca02c", "T2 Measurement": "#d62728",
        "Trap Mode": "#9467bd", "Bypass Mode": "#8c564b", 
        "Solenoid Status": "#e377c2", "Steam Leak": "#7f7f7f",
        "Water Log/Process Off": "#bcbd22", "Cooling Cycle Switch": "#17becf"
    }
}

param_choice = st.sidebar.selectbox("Parameter to Visualize", params_map[device])

# 3. DATA CONFIGURATION & LOADING
config = {
    "Mtrol 3": {"file": "Mtrol_3_11-13_March_2min_Average - Mtrol_3_11-13_March_2min_Average.csv.csv", "time": "Time Stamp", "temp": "Chamber Temperature (°C)"},
    "Mtrol 4": {"file": "Mtrol_4_11-13_March_2min_Average - Mtrol_4_11-13_March_2min_Average.csv.csv", "time": "Time Stamp", "temp": "Chamber Temperature (°C)"},
    "MUPT": {"file": "MUPT 1 - Sheet 1.csv", "time": "Timestamp"}
}

@st.cache_data
def load_data(dev):
    df = pd.read_csv(config[dev]["file"])
    df[config[dev]["time"]] = pd.to_datetime(df[config[dev]["time"]])
    return df

try:
    df = load_data(device)
    df_filtered = df.copy()

    # --- DYNAMIC FILTERS ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Data Filters")

    if device == "MUPT":
        # Ranges for C1, C2, T1, and T2 as requested
        mupt_filter_cols = ["C1 Measurement", "C2 Measurement", "T1 Measurement", "T2 Measurement"]
        for col in mupt_filter_cols:
            min_v, max_v = float(df[col].min()), float(df[col].max())
            r = st.sidebar.slider(f"Filter {col}", min_v, max_v, (min_v, max_v))
            df_filtered = df_filtered[(df_filtered[col] >= r[0]) & (df_filtered[col] <= r[1])]
    else:
        # Range for Mtrol Temperature
        target_temp = st.sidebar.slider("Target Temperature (°C)", -20.0, 80.0, 70.0, 0.5)
        tol = st.sidebar.slider("Tolerance (+/- °C)", 0.1, 5.0, 1.0)
        t_col = config[device]["temp"]
        df_filtered = df_filtered[(df_filtered[t_col] >= target_temp - tol) & (df_filtered[t_col] <= target_temp + tol)]

    # --- COLUMN MAPPING ---
    if "Mtrol" in device:
        mapping = {'1: Flow Rate': 'Flow Rate', '2: % Opening': '% Opening', '3: P1': 'P1', '4: P2': 'P2'}
        plot_col = mapping[param_choice]
    else:
        plot_col = param_choice

    time_col = config[device]["time"]

    if not df_filtered.empty:
        # CALCULATIONS
        mean_val = df_filtered[plot_col].mean()
        df_filtered['PPM'] = ((df_filtered[plot_col] - mean_val) / mean_val * 1_000_000) if mean_val != 0 else 0

        # --- 4. GRAPH WITH COLORS & LEGEND ---
        selected_color = color_palette[device][param_choice]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_filtered[time_col], 
            y=df_filtered['PPM'], 
            mode='lines+markers', 
            line=dict(color=selected_color, width=2),
            name=f"{device}: {param_choice}" # This label shows in the legend
        ))
        
        fig.update_layout(
            title=f"<b>{device} Stability: {plot_col}</b>",
            xaxis=dict(title="Time Stamp", rangeslider=dict(visible=True)), # X-Axis Label Restored
            yaxis=dict(title="PPM Deviation"), # Y-Axis Label Restored
            template="plotly_white",
            height=550,
            showlegend=True, # Force legend to show
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02, # Positioned slightly to the right of the graph
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="gray",
                borderwidth=1
            ),
            margin=dict(r=150) # Extra room on the right for the legend
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. STATISTICS (BETWEEN GRAPH & TABLE) ---
        st.markdown("### 📊 Statistics Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Mean Value", f"{mean_val:.4f}")
        c2.metric("Peak PPM", f"{df_filtered['PPM'].max():.2f}")
        c3.metric("Min PPM", f"{df_filtered['PPM'].min():.2f}")

        st.markdown("---") 
        
        # --- 6. DATA TABLE ---
        st.subheader("📋 Filtered Data Results")
        display_cols = [time_col, plot_col, 'PPM']
        # Add temp column if it's Mtrol
        if "Mtrol" in device: display_cols.insert(1, config[device]["temp"])
        
        st.dataframe(df_filtered[display_cols], use_container_width=True, hide_index=True)

    else:
        st.warning("No data found for the selected filter ranges. Please adjust the sidebar sliders.")

except Exception as e:
    st.error(f"Error: {e}")