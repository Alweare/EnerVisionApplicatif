from datetime import datetime, timezone

# `datetime.fromisoformat` (< 3.11) ne comprend pas le suffixe `Z` : on le
# remplace par l'offset UTC explicite avant parsing.
_UTC_ISO_SUFFIX = "+00:00"

SITE_TYPE_LABELS = {
    "office": "Bureau",
    "factory": "Usine",
    "datacenter": "Data center",
}

DATA_QUALITY_LABELS = {
    "good": "Données fiables",
    "partial": "Données partielles",
    "degraded": "Données dégradées",
    "critical": "Données critiques",
}

DATA_QUALITY_COLORS = {
    "good": "green",
    "partial": "orange",
    "degraded": "red",
    "critical": "red",
}

ALERT_SEVERITY_LABELS = {
    "low": "Faible",
    "medium": "Moyenne",
    "warning": "Avertissement",
    "high": "Élevée",
    "critical": "Critique",
}

ALERT_SEVERITY_COLORS = {
    "low": "blue",
    "medium": "orange",
    "warning": "orange",
    "high": "red",
    "critical": "red",
}

ALERT_SEVERITY_ORDER = ["low", "medium", "warning", "high", "critical"]

ALERT_TYPE_ORDER = ["spike", "threshold", "anomaly", "outage", "sensor", "consumption"]

ALERT_TYPE_COLORS = {
    "spike": "#2a78d6",        # bleu
    "threshold": "#eb6834",    # orange
    "anomaly": "#1baf7a",      # turquoise
    "outage": "#eda100",       # jaune
    "sensor": "#e87ba4",       # magenta
    "consumption": "#008300",  # vert
}

ALERT_TYPE_LABELS = {
    "spike": "Pic de consommation",
    "threshold": "Seuil dépassé",
    "anomaly": "Anomalie",
    "outage": "Coupure",
    "sensor": "Défaillance capteur",
    "consumption": "Consommation",
}


ACTION_TYPE_LABELS = {
    "shift_load": ("🕑", "Décaler la charge"),
    "reduce_load": ("⚡", "Délester la charge"),
    "notify": ("📣", "Alerter l'exploitant"),
}


RECOMMENDATION_STATUS_LABELS = {
    "pending": "À traiter",
    "applied": "Appliquée",
    "dismissed": "Ignorée",
}

# Ton du badge de statut (couleurs `st.badge`).
RECOMMENDATION_STATUS_COLORS = {
    "pending": "orange",
    "applied": "green",
    "dismissed": "gray",
}


# Fiabilité d'une reco, déduite de l'horizon de la prévision qui l'a produite
# (écart `predicted_for - created_at`). Une prévision à 1 h est plus sûre qu'à
# 1 semaine. Seuils calés sur les horizons du modèle (T+1h / T+24h / T+1 sem.).
RECOMMENDATION_CONFIDENCE_LABELS = {
    "high": "Fiable",
    "medium": "Probable",
    "low": "Indicatif",
}

RECOMMENDATION_CONFIDENCE_COLORS = {
    "high": "green",
    "medium": "orange",
    "low": "gray",
}


def action_type_label(action_type: str | None) -> str:
    """Libellé français d'une action de recommandation (ex. `shift_load`)."""
    if not action_type:
        return "Action recommandée"
    return ACTION_TYPE_LABELS.get(action_type, ("💡", action_type.replace("_", " ").capitalize()))[1]


def action_type_icon(action_type: str | None) -> str:
    """Emoji associé à une action de recommandation."""
    return ACTION_TYPE_LABELS.get(action_type, ("💡", ""))[0]


def recommendation_status_label(status: str | None) -> str:
    """Libellé français du statut d'une reco (ex. `applied` -> `Appliquée`)."""
    if not status:
        return "Statut inconnu"
    return RECOMMENDATION_STATUS_LABELS.get(status, status.capitalize())


def recommendation_status_color(status: str | None) -> str:
    """Couleur du badge de statut pour `st.badge` (`orange`, `green`, `gray`)."""
    return RECOMMENDATION_STATUS_COLORS.get(status, "gray")


def recommendation_confidence(
    predicted_for: str | datetime | None,
    created_at: str | datetime | None,
) -> str | None:
    """Niveau de fiabilité (`high`/`medium`/`low`) d'une reco, ou `None` si inconnu.

    Basé sur l'horizon de la prévision d'origine = `predicted_for - created_at` :
    ≤ 6 h → `high`, ≤ 48 h → `medium`, au-delà → `low`.
    """
    peak = _as_aware_utc(predicted_for)
    made = _as_aware_utc(created_at)
    if peak is None or made is None:
        return None
    lead_hours = (peak - made).total_seconds() / 3600
    if lead_hours <= 6:
        return "high"
    if lead_hours <= 48:
        return "medium"
    return "low"


def recommendation_confidence_label(level: str | None) -> str:
    """Libellé du badge de fiabilité (`Fiable` / `Probable` / `Indicatif`)."""
    return RECOMMENDATION_CONFIDENCE_LABELS.get(level, "Fiabilité inconnue")


def recommendation_confidence_color(level: str | None) -> str:
    """Couleur du badge de fiabilité pour `st.badge`."""
    return RECOMMENDATION_CONFIDENCE_COLORS.get(level, "gray")


def peak_within_hours(
    predicted_for: str | datetime | None,
    hours: float,
    *,
    now: datetime | None = None,
) -> bool:
    """`True` si le pic visé tombe dans les `hours` prochaines heures."""
    peak = _as_aware_utc(predicted_for)
    if peak is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (peak - now).total_seconds() <= hours * 3600


def site_type_label(site_type: str | None) -> str:
    if not site_type:
        return "Inconnu"
    return SITE_TYPE_LABELS.get(site_type, site_type.capitalize())


def data_quality_label(data_quality: str | None) -> str:
    if not data_quality:
        return "Qualité inconnue"
    return DATA_QUALITY_LABELS.get(data_quality, data_quality.capitalize())


def data_quality_color(data_quality: str | None) -> str:
    return DATA_QUALITY_COLORS.get(data_quality, "gray")


def is_data_reliable(data_quality: str | None) -> bool:
    return data_quality == "good"


def format_number(value: float | None, unit: str = "", decimals: int = 1) -> str:
    if value is None:
        return "—"
    formatted = f"{value:.{decimals}f}".replace(".", ",")
    return f"{formatted} {unit}".strip()


def format_power_factor(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _parse_iso_datetime(value: str) -> datetime:
    """Parse un horodatage ISO 8601, en acceptant le suffixe `Z` (UTC)."""
    return datetime.fromisoformat(value.replace("Z", _UTC_ISO_SUFFIX))


def format_time_of_day(moment: str | datetime | None) -> str:
    """Heure d'un horodatage au format `HH:MM` (ex. `18:00`)."""
    if moment is None:
        return "—"
    if isinstance(moment, str):
        moment = _parse_iso_datetime(moment)
    return moment.strftime("%H:%M")


def format_date_fr(moment: str | datetime | None) -> str:
    """Date d'un horodatage au format `JJ/MM/AAAA` (ex. `28/08/2026`)."""
    if moment is None:
        return "—"
    if isinstance(moment, str):
        moment = _parse_iso_datetime(moment)
    return moment.strftime("%d/%m/%Y")


def format_day_time(moment: str | datetime | None) -> str:
    """Jour et heure d'un horodatage au format `JJ/MM à HH:MM`
    (ex. `09/09 à 14:00`)."""
    if moment is None:
        return "—"
    if isinstance(moment, str):
        moment = _parse_iso_datetime(moment)
    return moment.strftime("%d/%m à %H:%M")


def site_option_label(site: dict) -> str:
    name = site.get("site_name") or site.get("site_id") or "Site"
    location = site.get("location")
    return f"{name} — {location}" if location else name

def _as_aware_utc(moment: str | datetime | None) -> datetime | None:
    """Parse une date (ISO string ou datetime) en `datetime` aware UTC, ou `None`.

    Une date naïve est supposée déjà en UTC (comme le stocke le backend).
    """
    if moment is None:
        return None
    if isinstance(moment, str):
        moment = _parse_iso_datetime(moment)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment

def relative_time(moment: str | datetime | None, *, now: datetime | None = None) -> str:
    # `_as_aware_utc` renvoie déjà un `datetime` aware UTC (ou `None`).
    moment = _as_aware_utc(moment)
    if moment is None:
        return "Date inconnue"

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    seconds = max(int((now - moment).total_seconds()), 0)
    if seconds < 45:
        return "Il y a quelques secondes"

    minutes = round(seconds / 60)
    if minutes <= 1:
        return "Il y a une minute"
    if minutes < 60:
        return f"Il y a {minutes} minutes"

    hours = round(minutes / 60)
    if hours == 1:
        return "Il y a une heure"
    if hours < 24:
        return f"Il y a {hours} heures"

    days = round(hours / 24)
    if days == 1:
        return "Il y a un jour"
    return f"Il y a {days} jours"


def alert_severity_label(severity: str | None) -> str:
    if not severity:
        return "Gravité inconnue"
    return ALERT_SEVERITY_LABELS.get(severity, severity.capitalize())


def alert_severity_color(severity: str | None) -> str:
    return ALERT_SEVERITY_COLORS.get(severity, "gray")


def alert_type_label(alert_type: str | None) -> str:
    if not alert_type:
        return "Type inconnu"
    return ALERT_TYPE_LABELS.get(alert_type, alert_type.capitalize())


def sort_alerts(alerts: list[dict]) -> list[dict]:

    return sorted(alerts, key=lambda alert: alert.get("created_at") or "", reverse=True)


def alert_counts_by_site_and_type(
    alerts: list[dict], site_labels: dict[str, str]
) -> list[dict]:

    counts: dict[tuple[str, str], int] = {}
    for alert in alerts:
        site_id = alert.get("site_id")
        alert_type = alert.get("type")
        if site_id in site_labels and alert_type in ALERT_TYPE_ORDER:
            counts[(site_id, alert_type)] = counts.get((site_id, alert_type), 0) + 1

    return [
        {
            "site": site_labels[site_id],
            "type": alert_type_label(alert_type),
            "nombre": counts.get((site_id, alert_type), 0),
        }
        for site_id in site_labels
        for alert_type in ALERT_TYPE_ORDER
    ]

def alert_type_palette() -> tuple[list[str], list[str]]:
    labels = [alert_type_label(t) for t in ALERT_TYPE_ORDER]
    colors = [ALERT_TYPE_COLORS[t] for t in ALERT_TYPE_ORDER]
    return labels, colors
