import streamlit as st

from authentification.auth import login_page, render_user_menu
from services.api_client import BackendUnavailableError, get

st.set_page_config(page_title="EnerVision", page_icon="⚡", layout="wide")

# Non authentifié : une seule "page" (l'écran de connexion), navigation masquée.
# Le menu et les pages applicatives ne sont jamais construits -> aucun accès
# possible au dashboard, aux sites, etc. tant qu'on n'est pas connecté.
if not st.user.is_logged_in:
    st.navigation([st.Page(login_page, title="Connexion")], position="hidden").run()
    st.stop()

# --- À partir d'ici : utilisateur authentifié ---
st.logo("assets/enervision_logo.svg")

# En-tête : menu utilisateur aligné à droite, au-dessus du contenu des pages.
_, header_user = st.columns([5, 1], vertical_alignment="center")
with header_user:
    render_user_menu()

try:
    me = get("/api/v1/me")
except BackendUnavailableError:
    st.sidebar.error("Backend indisponible.")

dashboard_page = st.Page("pages/dashboard.py", title="Dashboard", default=True)
sites_page = st.Page("pages/sites.py", title="Sites")

st.navigation([dashboard_page, sites_page]).run()
