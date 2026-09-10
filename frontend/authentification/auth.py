import streamlit as st

#test
def login_page() -> None:
    """Écran de connexion : seul contenu visible tant qu'on n'est pas authentifié."""
    st.title("EnerVision")
    st.write("Connectez-vous avec votre compte pour accéder au dashboard.")
    if st.button("Se connecter", type="primary"):
        st.login()


def require_authentication() -> None:
    """Défense par page : bloque l'accès tant que l'utilisateur n'est pas authentifié.

    L'entrée dans l'app est déjà gardée par `app.py` ; cet appel protège les
    pages contre un accès direct par URL.
    """
    if st.user.is_logged_in:
        return

    login_page()
    st.stop()


def render_user_menu() -> None:
    """Menu utilisateur compact (identité + déconnexion), à placer dans l'en-tête.

    Rendu volontairement hors sidebar : `st.navigation` occupe le haut de la
    sidebar, l'identité passait sous le menu et donnait un rendu bancal.
    """
    display_name = (
        getattr(st.user, "name", None)
        or getattr(st.user, "preferred_username", None)
        or getattr(st.user, "email", None)
        or "Utilisateur"
    )
    with st.popover(f"👤 {display_name}", use_container_width=True):
        st.write(f"Connecté en tant que **{display_name}**")
        if st.button("Déconnexion", use_container_width=True):
            st.logout()


def get_access_token() -> str | None:
    """Access token Keycloak de l'utilisateur courant, pour appeler backend/core."""
    try:
        return st.user.tokens["access"]
    except (KeyError, AttributeError):
        return None
