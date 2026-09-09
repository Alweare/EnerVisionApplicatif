import streamlit as st

from formatting import relative_time

QUALITY_LABEL = {
    "good": ("🟢", "Données fiables"),
    "partial": ("🟠", "Données dégradées"),
    "degraded": ("🟠", "Données dégradées"),
    "critical": ("🔴", "Données critiques"),
}


def render_site_card(site: dict, on_select=None) -> None:
    is_active = site["status"] == "active"

    with st.container(border=True):
        col_info, col_metric, col_action = st.columns([3, 2, 1])

        with col_info:
            if is_active:
                st.markdown(f"**{site['site_name']}**")
            else:
                st.markdown(f"<span style='color:grey'>{site['site_name']}</span>", unsafe_allow_html=True)
                st.caption("🔒 Inactif")
            st.caption(f"{site['location']} · Capacité : {site['capacity_kw']} kW")

        with col_metric:
            measured_at = site.get("measurement_date")
            if is_active and site.get("current_consumption_kw") is not None:
                icon, label = QUALITY_LABEL.get(site.get("data_quality", "good"), ("⚪", "Inconnu"))
                st.metric("Consommation actuelle", f"{site['current_consumption_kw']} kW")
                st.caption(f"{icon} {label}")
                st.caption(f"🕓 {relative_time(measured_at)}")
            elif is_active:
                st.caption("— donnée indisponible")
                if measured_at:
                    st.caption(f"🕓 {relative_time(measured_at)}")

        with col_action:
            if on_select is None:
                return
            if is_active:
                if st.button("Voir le détail", key=f"goto_{site['site_id']}"):
                    on_select(site["site_id"])
            else:
                st.button("Voir le détail", key=f"goto_{site['site_id']}", disabled=True)