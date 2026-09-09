import time

import streamlit as st

from formatting import (
    action_type_icon,
    action_type_label,
    format_number,
    peak_within_hours,
    recommendation_confidence,
    recommendation_confidence_color,
    recommendation_confidence_label,
    recommendation_status_color,
    recommendation_status_label,
    site_option_label,
)
from services.api_client import BackendUnavailableError
from services.recommendation_service import (
    get_my_recommendations,
    refresh_my_recommendations,
    set_recommendation_status,
)
from services.site_service import get_my_sites

# Recalcule les recos avant l'affichage, au plus une fois toutes les
# _REFRESH_TTL secondes par session : le script Streamlit se ré-exécute à
# chaque interaction (ex. le selectbox), on ne veut pas relancer le moteur
# à chaque rerun.
_REFRESH_TTL = 300

# Filtres proposés au-dessus de la liste ; `None` = tous les statuts.
_STATUS_FILTERS = {
    "pending": "À traiter",
    "applied": "Appliquées",
    "dismissed": "Ignorées",
    None: "Toutes",
}

# Filtre par échéance du pic ; la valeur est un nombre d'heures, `None` = tout.
_DEADLINE_FILTERS = {
    None: "Toutes",
    24: "Prochaines 24 h",
    24 * 7: "Prochaine semaine",
}

# Transitions proposées depuis un statut donné : (statut cible, libellé, icône).
_STATUS_ACTIONS = {
    "pending": [
        ("applied", "Marquer appliquée", "✅"),
        ("dismissed", "Ignorer", "🚫"),
    ],
    "applied": [("pending", "Rouvrir", "↩️")],
    "dismissed": [("pending", "Rouvrir", "↩️")],
}


def _refresh_recommendations_if_stale() -> None:
    last = st.session_state.get("recommendations_refreshed_at", 0.0)
    if time.monotonic() - last < _REFRESH_TTL:
        return
    try:
        refresh_my_recommendations()
        st.session_state["recommendations_refreshed_at"] = time.monotonic()
    except BackendUnavailableError:
        # Pas bloquant : on affiche les recos déjà en base, le prochain
        # rerun retentera.
        pass


def _update_status(recommendation_id: str, new_status: str) -> None:
    """Callback de bouton : change le statut d'une reco puis laisse Streamlit relancer."""
    try:
        set_recommendation_status(recommendation_id, new_status)
    except BackendUnavailableError:
        st.toast("Impossible de mettre à jour la recommandation.", icon="⚠️")
        return
    st.toast(
        f"Recommandation « {recommendation_status_label(new_status)} ».", icon="✅"
    )


st.title("Mes recommandations")
st.caption(
    "Générées à partir des pics de consommation prévus sur vos sites. "
    "Chaque recommandation propose une action concrète, et un gain estimé "
    "quand il est chiffrable."
)

_refresh_recommendations_if_stale()

try:
    sites = get_my_sites()
except BackendUnavailableError as error:
    st.error(f"Impossible de récupérer vos sites : {error}")
    st.stop()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {site["site_id"]: site for site in sites}

col_site, col_deadline = st.columns([2, 2])
with col_site:
    selected_site_id = st.selectbox(
        "Site",
        options=list(sites_by_id),
        format_func=lambda site_id: site_option_label(sites_by_id[site_id]),
    )
with col_deadline:
    selected_deadline = st.selectbox(
        "Échéance",
        options=list(_DEADLINE_FILTERS),
        format_func=lambda hours: _DEADLINE_FILTERS[hours],
    )

selected_status = st.radio(
    "Statut",
    options=list(_STATUS_FILTERS),
    format_func=lambda status: _STATUS_FILTERS[status],
    horizontal=True,
)

st.caption(
    "⏱️ La fiabilité reflète l'horizon de prévision : « Fiable » ≈ pic à quelques "
    "heures, « Probable » ≈ le lendemain, « Indicatif » ≈ plusieurs jours."
)

try:
    my_recommendations = get_my_recommendations(status=selected_status)
except BackendUnavailableError as error:
    st.error(f"Impossible de récupérer vos recommandations : {error}")
    st.stop()

recommendations = [
    reco
    for reco in my_recommendations
    if reco["site_id"] == selected_site_id
    and (
        selected_deadline is None
        or peak_within_hours(reco.get("predicted_for"), selected_deadline)
    )
]

if not recommendations:
    if selected_status == "pending" and selected_deadline is None:
        st.info(
            "Aucune recommandation à traiter pour ce site : aucune règle ne se "
            "déclenche à cet instant (pas de pic de consommation prévu)."
        )
    else:
        st.info("Aucune recommandation pour ce site avec ces filtres.")
    st.stop()

for reco in recommendations:
    status = reco.get("status", "pending")
    confidence = recommendation_confidence(
        reco.get("predicted_for"), reco.get("created_at")
    )
    with st.container(border=True):
        col_title, col_badges = st.columns([3, 2], vertical_alignment="center")
        with col_title:
            st.markdown(
                f"### {action_type_icon(reco['action_type'])} "
                f"{action_type_label(reco['action_type'])}"
            )
        with col_badges:
            st.badge(
                recommendation_status_label(status),
                color=recommendation_status_color(status),
            )
            if confidence is not None:
                st.badge(
                    recommendation_confidence_label(confidence),
                    icon="⏱️",
                    color=recommendation_confidence_color(confidence),
                )

        if reco.get("message"):
            st.write(reco["message"])

        gain = reco.get("estimated_gain_kw")
        if gain is not None:
            st.success(f"Gain estimé : ≈ {format_number(gain, 'kW')} à effacer en pointe")

        actions = _STATUS_ACTIONS.get(status, [])
        if actions:
            for col, (target_status, label, icon) in zip(st.columns(len(actions)), actions):
                col.button(
                    f"{icon} {label}",
                    key=f"{target_status}-{reco['recommendation_id']}",
                    on_click=_update_status,
                    args=(reco["recommendation_id"], target_status),
                    use_container_width=True,
                )
