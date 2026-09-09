"""Fonctions de mise en forme pour l'affichage du dashboard (aucune I/O)."""

from datetime import datetime, timezone

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


def site_option_label(site: dict) -> str:
    name = site.get("site_name") or site.get("site_id") or "Site"
    location = site.get("location")
    return f"{name} — {location}" if location else name


def relative_time(moment: str | datetime | None, *, now: datetime | None = None) -> str:
    if moment is None:
        return "Date inconnue"
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

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
