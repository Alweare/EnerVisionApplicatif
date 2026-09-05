from datetime import datetime

import streamlit as st

from services.measurement_service import get_current_measurement, get_measurement_history
from services.site_service import get_sites

sites = get_sites()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

site_names = {s["site_name"]: s["site_id"] for s in sites}
selected_name = st.selectbox("Site", list(site_names.keys()))
selected_site_id = site_names[selected_name]

@st.fragment(run_every="60s")
def show_current_measurement(site_id: str) -> None:
    current = get_current_measurement(site_id)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Consommation actuelle", f"{current['consumption_kw']} kW")
    with col2:
        st.metric("Température", f"{current['temperature_celsius']} °C")
    with col3:
        st.metric("Qualité des données", current["data_quality"])
    st.caption(f"Dernière mise à jour : {datetime.now():%H:%M:%S}")


@st.fragment(run_every="60s")
def show_history(site_id: str) -> None:
    st.subheader("Historique")
    history = get_measurement_history(site_id)
    st.line_chart(history, x="measurement_date", y="consumption_kw")


show_current_measurement(selected_site_id)
show_history(selected_site_id)