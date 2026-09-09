import streamlit as st

LOGO = "assets/enervision_logo.svg"


def render_logo() -> None:
    st.logo(LOGO, size="large")
