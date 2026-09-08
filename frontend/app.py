import streamlit as st

from authentification.auth import login_page, render_user_menu
from branding import render_logo
from services.api_client import BackendUnavailableError, get

st.set_page_config(page_title="EnerVision", page_icon="⚡", layout="wide")

# Avant la porte d'authentification : l'écran de connexion a le même en-tête
# que les pages internes.
render_logo()

# Non authentifié : une seule "page" (l'écran de connexion), navigation masquée.
# Le menu et les pages applicatives ne sont jamais construits -> aucun accès
# possible au dashboard, aux sites, etc. tant qu'on n'est pas connecté.
if not st.user.is_logged_in:
    st.navigation([st.Page(login_page, title="Connexion")], position="hidden").run()
    st.stop()


# En-tête : menu utilisateur aligné à droite, au-dessus du contenu des pages.
_, header_user = st.columns([5, 1], vertical_alignment="center")
with header_user:
    render_user_menu()

try:
    get("/api/v1/me")
except BackendUnavailableError:
    st.sidebar.error("Backend indisponible.")

dashboard_page = st.Page("pages/dashboard.py", title="Dashboard", default=True)
sites_page = st.Page("pages/sites.py", title="Sites")
recommandations_page = st.Page("pages/recommandations.py", title="Recommandations")
alertes_page = st.Page("pages/alertes.py", title="Alertes")

pg = st.navigation([dashboard_page, sites_page, recommandations_page, alertes_page])
pg.run()