# Mtrol Analysis Cloud 🚀

An advanced data synchronization and analytics platform designed to evaluate the precision stability of Mtrol devices over extended thermal cycles.

## 🌟 Key Features
* **Automated Sync:** Merges 1-second device telemetry with 2-minute chamber temperature logs.
* **Smart Filtering:** Pre-configured for the March 11–13 precision window.
* **Performance Optimized:** Uses WebGL (Scattergl) to handle hundreds of thousands of data points with zero cursor lag.
* **PPM Calculation:** Automated thermal stability (PPM) math for P1, P2, Flow, and Opening.
* **Interactive UI:** Dynamic scaling and dual-axis visualization.

## 🛠️ Setup & Deployment
1. **Clone the repo:** `git clone https://github.com/[YOUR_USERNAME]/mtrol-analysis-cloud.git`
2. **Install requirements:** `pip install -r requirements.txt`
3. **Run locally:** `streamlit run app.py`

## 📊 Data Requirements
The application expects two CSV files:
1. **Device CSV:** Contains 'Time Stamp', 'P1', 'P2', 'Flow Rate', and '% Opening'.
2. **Chamber CSV:** Contains 'Timestamp' and 'Temperature (°C)(Temp)'.