import streamlit as st

from authentification.auth import render_user_menu, require_authentication
from services.api_client import BackendUnavailableError, get

st.set_page_config(page_title="EnerVision", page_icon="⚡", layout="wide")
st.logo("assets/enervision_logo.svg")

require_authentication()
render_user_menu()

try:
    me = get("/api/v1/me")
except BackendUnavailableError:
    st.sidebar.error("Backend indisponible.")
else:
    st.sidebar.caption(f"Identité vérifiée par l'API : {me.get('username') or me.get('sub')}")

st.title("EnerVision — Dashboard")

dashboard_page = st.Page("pages/Dashboard.py", title="Dashboard", default=True)
alertes_page = st.Page("pages/Alertes.py", title="Alertes")

pg = st.navigation([dashboard_page, alertes_page])
pg.run()
