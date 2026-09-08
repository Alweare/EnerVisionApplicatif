import streamlit as st

from authentification.auth import render_user_menu, require_authentication
from branding import render_logo
from services.api_client import BackendUnavailableError, get

st.set_page_config(page_title="EnerVision", page_icon="⚡", layout="wide")

render_logo()

require_authentication()
render_user_menu()

try:
    me = get("/api/v1/me")
except BackendUnavailableError:
    st.sidebar.error("Backend indisponible.")
else:
    st.sidebar.caption(f"Identité vérifiée par l'API : {me.get('username') or me.get('sub')}")

dashboard_page = st.Page("pages/dashboard.py", title="Dashboard", default=True)
sites_page = st.Page("pages/sites.py", title="Sites")
alertes_page = st.Page("pages/alertes.py", title="Alertes")

pg = st.navigation([dashboard_page, sites_page, alertes_page])
pg.run()
