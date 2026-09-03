import streamlit as st

def render_not_found(message: str = "Cette ressource n'existe pas ou n'est plus disponible.") -> None:
    st.error(f"404 — {message}")
    st.write("Vérifiez le lien, ou retournez au dashboard.")
    if st.button("Retour au dashboard"):
        st.switch_page("app.py")