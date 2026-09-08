import streamlit as st

st.title("EnerVision — Dashboard")

from services.measurement_service import get_current_measurement, get_measurement_history
from services.site_service import get_my_sites

sites = get_my_sites(active_only=True)

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

site_names = {s["site_name"]: s["site_id"] for s in sites}
names_list = list(site_names.keys())

# Pré-sélection si on arrive depuis "Mes sites" (bouton "Voir le détail")
preselected_id = st.session_state.get("selected_site_id")
default_index = 0
if preselected_id:
    for i, (name, sid) in enumerate(site_names.items()):
        if sid == preselected_id:
            default_index = i
            break

selected_name = st.selectbox("Site", names_list, index=default_index)
selected_site_id = site_names[selected_name]

current = get_current_measurement(selected_site_id)

col1, col2 = st.columns(2)
with col1:
    if current and current.get("consumption_kw") is not None:
        st.metric("Consommation actuelle", f"{current['consumption_kw']} kW")
    else:
        st.metric("Consommation actuelle", "—")
with col2:
    if current:
        st.metric("Qualité des données", current.get("data_quality", "inconnue"))
    else:
        st.metric("Qualité des données", "indisponible")

st.subheader("Historique")
history = get_measurement_history(selected_site_id)
if not history:
    st.info("Aucune donnée d'historique disponible pour ce site.")
else:
    st.line_chart(history, x="measurement_date", y="consumption_kw")