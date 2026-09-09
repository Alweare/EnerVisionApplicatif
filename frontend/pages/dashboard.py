import streamlit as st

from authentification.auth import require_authentication
from branding import render_logo

require_authentication()
render_logo()

st.title("EnerVision — Dashboard")

from formatting import (
    data_quality_color,
    data_quality_label,
    format_number,
    format_power_factor,
    is_data_reliable,
    relative_time,
    site_option_label,
    site_type_label,
)
from services.api_client import BackendUnavailableError
from services.measurement_service import get_current_measurement, get_measurement_history
from services.site_service import get_my_sites

try:
    sites = get_my_sites(active_only=True)
except BackendUnavailableError as error:
    st.error(f"Impossible de récupérer vos sites : {error}")
    st.stop()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {s["site_id"]: s for s in sites}

# Pré-sélection si on arrive depuis "Mes sites" (bouton "Voir le détail").
preselected_id = st.session_state.get("selected_site_id")
options = list(sites_by_id)
default_index = options.index(preselected_id) if preselected_id in sites_by_id else 0

selected_site_id = st.selectbox(
    "Site",
    options=options,
    index=default_index,
    format_func=lambda site_id: site_option_label(sites_by_id[site_id]),
)
selected_site = sites_by_id[selected_site_id]


@st.fragment(run_every="60s")
def show_current_measurement(site: dict) -> None:
    try:
        current = get_current_measurement(site["site_id"])
    except BackendUnavailableError:
        st.warning("Mesure en temps réel indisponible pour le moment.")
        return
    if current is None:
        st.info("Aucune mesure disponible pour ce site.")
        return

    data_quality = current.get("data_quality")

    with st.container(border=True):
        value_col, status_col = st.columns([2, 1])
        with value_col:
            st.caption("Consommation actuelle")
            st.markdown(f"## {format_number(current.get('consumption_kw'), 'kW')}")
        with status_col:
            st.badge(
                data_quality_label(data_quality),
                icon=(
                    ":material/check_circle:"
                    if is_data_reliable(data_quality)
                    else ":material/warning:"
                ),
                color=data_quality_color(data_quality),
            )
            st.caption(relative_time(current.get("measurement_date")))

        left_col, right_col = st.columns(2)
        left_col.write(
            f"Facteur de puissance **{format_power_factor(current.get('power_factor'))}**"
        )
        right_col.write(f"Type de site **{site_type_label(site.get('site_type'))}**")


@st.fragment(run_every="60s")
def show_history(site_id: str) -> None:
    st.subheader("Historique")
    try:
        history = get_measurement_history(site_id)
    except BackendUnavailableError as error:
        st.error(f"Impossible de récupérer l'historique des mesures : {error}")
        return
    if not history:
        st.info("Aucune donnée d'historique disponible pour ce site.")
        return
    st.line_chart(history, x="measurement_date", y="consumption_kw")


show_current_measurement(selected_site)
show_history(selected_site_id)
