import streamlit as st

from authentification.auth import require_authentication
from branding import render_logo
from services.site_service import get_my_sites
from components.site_card import render_site_card
from services.api_client import BackendUnavailableError

require_authentication()
render_logo()

st.title("Mes sites")

try:
    sites = get_my_sites(active_only=False)
except BackendUnavailableError as e:
    st.error(f"Impossible de récupérer vos sites : {e}")
    st.stop()

if not sites:
    st.info("Aucun site associé à votre compte pour le moment.")
    st.stop()


def go_to_dashboard(site_id: str) -> None:
    st.session_state["selected_site_id"] = site_id
    st.switch_page("pages/dashboard.py")


for site in sites:
    render_site_card(site, on_select=go_to_dashboard)