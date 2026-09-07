"""Authentification du frontend via Keycloak (OpenID Connect, Authorization Code Flow).

L'utilisateur saisit son identifiant/mot de passe uniquement sur Keycloak :
Streamlit ne reçoit et ne stocke jamais le mot de passe. La session est gérée
nativement par Streamlit (st.login / st.logout / st.user), sans mécanisme
parallèle.
"""

import streamlit as st


def require_authentication() -> None:
    """Bloque l'accès à la page tant que l'utilisateur n'est pas authentifié.

    À appeler en tout premier, avant tout contenu métier.
    """
    if st.user.is_logged_in:
        return

    st.title("EnerVision")
    st.write("Connectez-vous avec votre compte pour accéder au dashboard.")
    if st.button("Se connecter", type="primary"):
        st.login()
    st.stop()


def render_user_menu() -> None:
    """Affiche l'utilisateur connecté et un bouton de déconnexion dans la sidebar."""
    display_name = (
        getattr(st.user, "name", None)
        or getattr(st.user, "preferred_username", None)
        or getattr(st.user, "email", None)
        or "Utilisateur"
    )
    with st.sidebar:
        st.write(f"Connecté en tant que **{display_name}**")
        if st.button("Déconnexion"):
            st.logout()


def get_access_token() -> str | None:
    """Access token Keycloak de l'utilisateur courant, pour appeler backend/core.

    Ne jamais logger, afficher ou persister la valeur retournée.
    """
    try:
        return st.user.tokens["access"]
    except (KeyError, AttributeError):
        return None
