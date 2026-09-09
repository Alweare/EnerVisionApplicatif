from datetime import datetime, timedelta, timezone

import altair as alt
import pandas as pd
import streamlit as st

from authentification.auth import require_authentication
from branding import render_logo
from formatting import (
    ALERT_SEVERITY_ORDER,
    alert_counts_by_site_and_type,
    alert_severity_color,
    alert_severity_label,
    alert_type_label,
    alert_type_palette,
    format_number,
    relative_time,
    site_option_label,
    sort_alerts,
)
from services.alert_service import get_alerts
from services.site_service import get_my_sites

require_authentication()
render_logo()

st.header("Alertes")

TOUS_LES_SITES = "__all__"
FENETRE_JOURS = 30

ENCRE = "#0b0b0b"
ENCRE_SECONDAIRE = "#52514e"

sites = get_my_sites()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {s["site_id"]: s for s in sites}


def filter_label(site_id: str) -> str:
    if site_id == TOUS_LES_SITES:
        return "Tous les sites"
    return site_option_label(sites_by_id[site_id])


selected_site_id = st.selectbox(
    "Site",
    options=[TOUS_LES_SITES, *sites_by_id],
    format_func=filter_label,
)

selected_severities = st.pills(
    "Gravité",
    options=ALERT_SEVERITY_ORDER,
    format_func=alert_severity_label,
    selection_mode="multi",
    help="Aucune sélection = toutes les gravités.",
)


def show_alert(alert: dict, *, with_site: bool) -> None:
    with st.container(border=True):
        header_col, badge_col = st.columns([4, 1])
        with header_col:
            st.markdown(f"**{alert_type_label(alert.get('type'))}**")
            st.caption(alert.get("message") or "Aucun message.")
        with badge_col:
            st.badge(
                alert_severity_label(alert.get("severity")),
                color=alert_severity_color(alert.get("severity")),
            )
            st.caption(relative_time(alert.get("created_at")))

        value_col, threshold_col, site_col = st.columns(3)
        value_col.write(f"Valeur **{format_number(alert.get('value'), 'kW')}**")
        threshold_col.write(f"Seuil **{format_number(alert.get('threshold'), 'kW')}**")
        if with_site:
            site = sites_by_id.get(alert.get("site_id"), {})
            site_col.write(
                f"Site **{site.get('site_name') or alert.get('site_id') or '—'}**"
            )


@st.fragment(run_every="60s")
def show_histogram(site_id: str, severities: list[str]) -> None:
    """Un histogramme par site : nombre d'alertes de chaque type sur la fenêtre."""
    depuis = datetime.now(timezone.utc) - timedelta(days=FENETRE_JOURS)
    alerts = get_alerts(
        site_id=None if site_id == TOUS_LES_SITES else site_id,
        since=depuis,
        severities=severities,
        limit=1000,
    )

    if not alerts:
        st.info(
            f"Aucune alerte sur les {FENETRE_JOURS} derniers jours "
            "pour ces critères."
        )
        return

    site_labels = (
        {sid: site.get("site_name") or sid for sid, site in sites_by_id.items()}
        if site_id == TOUS_LES_SITES
        else {site_id: sites_by_id[site_id].get("site_name") or site_id}
    )
    counts = pd.DataFrame(alert_counts_by_site_and_type(alerts, site_labels))
    types, couleurs = alert_type_palette()

    base = alt.Chart(counts).encode(
        y=alt.Y(
            "type:N",
            sort=types,
            title=None,
            axis=alt.Axis(
                domain=False, ticks=False, labelColor=ENCRE_SECONDAIRE, labelFontSize=11
            ),
        ),

        x=alt.X("nombre:Q", title=None, axis=None),
    )
    barres = base.mark_bar(cornerRadiusEnd=4, size=13).encode(
        color=alt.Color(
            "type:N",
            scale=alt.Scale(domain=types, range=couleurs),
            legend=alt.Legend(
                orient="bottom",
                title=None,
                columns=3,
                labelColor=ENCRE_SECONDAIRE,
                labelFontSize=11,
                symbolType="square",
                symbolSize=110,
            ),
        ),
        tooltip=[
            alt.Tooltip("site:N", title="Site"),
            alt.Tooltip("type:N", title="Type"),
            alt.Tooltip("nombre:Q", title="Alertes"),
        ],
    )

    valeurs = (
        base.transform_filter(alt.datum.nombre > 0)
        .mark_text(align="left", dx=5, color=ENCRE_SECONDAIRE, fontSize=11)
        .encode(text="nombre:Q")
    )

    chart = (
        (barres + valeurs)
        .properties(width=210, height=alt.Step(20))
        .facet(
            facet=alt.Facet(
                "site:N",
                title=None,
                header=alt.Header(
                    labelFontSize=13,
                    labelFontWeight=600,
                    labelColor=ENCRE,
                    labelAnchor="start",
                    labelPadding=6,
                ),
            ),
            columns=2,
            spacing={"row": 24, "column": 36},
        )
        .configure_view(stroke=None)
    )
    st.altair_chart(chart)

    if st.toggle("Voir les chiffres", key="chiffres_alertes"):
        st.dataframe(
            counts.pivot(index="type", columns="site", values="nombre").reindex(types),
            use_container_width=True,
        )


@st.fragment(run_every="60s")
def show_alerts(site_id: str, severities: list[str]) -> None:
    alerts = get_alerts(
        site_id=None if site_id == TOUS_LES_SITES else site_id,
        severities=severities,
    )

    if not alerts:
        st.info(
            "Aucune alerte enregistrée."
            if site_id == TOUS_LES_SITES
            else "Aucune alerte enregistrée pour ce site."
        )
        return

    st.caption(f"{len(alerts)} alerte(s)")
    for alert in sort_alerts(alerts):
        show_alert(alert, with_site=site_id == TOUS_LES_SITES)


with st.expander(
        f"Répartition sur les {FENETRE_JOURS} derniers jours", expanded=True
):
    show_histogram(selected_site_id, selected_severities)

with st.expander("Détail des alertes", expanded=False):
    show_alerts(selected_site_id, selected_severities)
