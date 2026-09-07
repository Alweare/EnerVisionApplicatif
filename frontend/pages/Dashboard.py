import streamlit as st

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
from services.measurement_service import get_current_measurement, get_measurement_history
from services.site_service import get_sites

st.header("Dashboard")

sites = get_sites()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {s["site_id"]: s for s in sites}
selected_site_id = st.selectbox(
    "Site",
    options=list(sites_by_id),
    format_func=lambda site_id: site_option_label(sites_by_id[site_id]),
)
selected_site = sites_by_id[selected_site_id]


@st.fragment(run_every="60s")
def show_current_measurement(site: dict) -> None:
    current = get_current_measurement(site["site_id"])
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
    history = get_measurement_history(site_id)
    if not history:
        st.info("Aucune mesure disponible pour ce site.")
        return
    st.line_chart(history, x="measurement_date", y="consumption_kw")


show_current_measurement(selected_site)
show_history(selected_site_id)
