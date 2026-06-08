import streamlit as st
import os
import requests
from datetime import datetime

# Optional: Load env vars for local testing
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="AIPP Operator Dashboard", layout="wide")

# Clean Light Theme CSS
st.markdown("""
<style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Main Title */
    h1 {
        font-weight: 700 !important;
        letter-spacing: -0.5px;
        color: #1e293b !important;
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }
    
    /* Subheaders */
    h2, h3 {
        color: #334155 !important;
        font-weight: 600 !important;
        letter-spacing: -0.3px;
        margin-top: 1.5rem !important;
    }
    
    /* Divider */
    hr {
        margin-top: 2rem;
        margin-bottom: 2rem;
        border-color: #f1f5f9;
    }
    
    /* Metric Cards Styling */
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 16px 20px;
        border-radius: 8px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    
    /* Metric Labels */
    div[data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Metric Values */
    div[data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
    }
    
    /* Dataframes */
    [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
col_logo, col_title = st.columns([1, 10])
with col_logo:
    try:
        st.image("mascot.png", width=80)
    except Exception:
        pass
with col_title:
    st.title("AIPP Operator Dashboard")
    st.markdown("<p style='color: #64748b; font-size: 0.95rem; margin-top: -10px; margin-bottom: 30px;'>Agent-Native Lightning Payment Infrastructure</p>", unsafe_allow_html=True)

# Configuration
col_auth1, col_auth2 = st.columns(2)

# Read from query parameters or environment
query_token = st.query_params.get("token", "")
env_token = os.getenv("SATSGATE_ADMIN_TOKEN", "")
default_token = query_token if query_token else env_token

BASE_URL = col_auth1.text_input("Satsgate URL", value=os.getenv("SATSGATE_URL", "http://satsgate:8000"))
ADMIN_TOKEN = col_auth2.text_input("Admin Token", value=default_token, type="password")

if ADMIN_TOKEN:
    st.query_params["token"] = ADMIN_TOKEN

if not ADMIN_TOKEN:
    st.info("Please enter the Admin Token to view the dashboard.")
    st.stop()

def fetch_overview(base_url: str, token: str):
    headers = {
        "X-Admin-Token": token
    }
    try:
        response = requests.get(f"{base_url}/v1/admin/overview", headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch overview: {e}")
        return None

if st.button("Refresh Data"):
    st.rerun()

data = fetch_overview(BASE_URL, ADMIN_TOKEN)

if data and data.get("ok"):
    overview = data["overview"]
    
    # --- TOP KPI METRICS ---
    st.markdown("<h2 style='margin-top: 0;'>Core Metrics</h2>", unsafe_allow_html=True)
    totals = overview["totals"]
    window = overview["window"]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Revenue (Sats)", f"{window['topups_sats_sum']:,}", "Last 24h")
    col2.metric("Total Agents", totals["clients_total"])
    col3.metric("API Verifications", f"{window['verify_events']:,}", "Last 24h")
    col4.metric("Outstanding Credits", f"{totals['credits_outstanding']:,}")
    
    st.divider()

    # --- CHARTS ---
    st.markdown("<h2>Trends (Last 7 Days)</h2>", unsafe_allow_html=True)
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Lightning Revenue (Sats)")
        if overview.get("daily_topups"):
            import pandas as pd
            df_topups = pd.DataFrame(overview["daily_topups"])
            if not df_topups.empty:
                df_topups['day'] = pd.to_datetime(df_topups['day'])
                df_topups.set_index('day', inplace=True)
                st.area_chart(df_topups['sats_sum'], color="#475569")
            else:
                st.info("No lightning revenue in the last 7 days.")
        else:
            st.info("No data available.")

    with col_chart2:
        st.subheader("API Verifications")
        if overview.get("daily_verifications"):
            import pandas as pd
            df_verif = pd.DataFrame(overview["daily_verifications"])
            if not df_verif.empty:
                df_verif['day'] = pd.to_datetime(df_verif['day'])
                df_verif.set_index('day', inplace=True)
                st.bar_chart(df_verif['count'], color="#94a3b8")
            else:
                st.info("No API verifications in the last 7 days.")
        else:
            st.info("No data available.")

    st.divider()

    # --- RECENT TRANSACTIONS ---
    st.markdown("<h2>Live Feed</h2>", unsafe_allow_html=True)
    col_feed1, col_feed2 = st.columns(2)
    
    with col_feed1:
        st.subheader("Recent Lightning Topups")
        recent_topups = overview.get("recent_topups", [])
        if recent_topups:
            import pandas as pd
            df_t = pd.DataFrame(recent_topups)
            
            # Create avatar URLs based on client_id (DiceBear Identicons)
            df_t['avatar'] = df_t['client_id'].apply(lambda x: f"https://api.dicebear.com/7.x/identicon/svg?seed={x}&backgroundColor=f8fafc")
            
            df_t = df_t[['avatar', 'created_iso', 'client_id', 'sats', 'status']]
            
            st.dataframe(
                df_t, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "avatar": st.column_config.ImageColumn("Icon"),
                    "created_iso": "Date",
                    "client_id": "Agent ID",
                    "sats": "Sats",
                    "status": "Status"
                }
            )
        else:
            st.info("No recent topups.")

    with col_feed2:
        st.subheader("Recent API Paywalls")
        recent_verifs = overview.get("recent_verifications", [])
        if recent_verifs:
            import pandas as pd
            df_v = pd.DataFrame(recent_verifs)
            
            # Create avatar URLs based on client_id
            df_v['avatar'] = df_v['client_id'].apply(lambda x: f"https://api.dicebear.com/7.x/identicon/svg?seed={x}&backgroundColor=f8fafc")
            
            df_v['delta_credits'] = df_v['delta_credits'].abs()
            df_v = df_v[['avatar', 'created_iso', 'client_id', 'delta_credits']]
            
            st.dataframe(
                df_v, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "avatar": st.column_config.ImageColumn("Icon"),
                    "created_iso": "Date",
                    "client_id": "Agent ID",
                    "delta_credits": "Credits Spent"
                }
            )
        else:
            st.info("No recent API verifications.")

    st.divider()
    
    last_seen = overview["last_seen"]
    st.caption(f"**Last Settled Topup:** {last_seen['topup_settled_iso'] or 'N/A'}")
    st.caption(f"**Last Paywall Verification:** {last_seen['verify_iso'] or 'N/A'}")

else:
    st.error("Invalid response from Satsgate or Unauthorized. Please check your token.")
