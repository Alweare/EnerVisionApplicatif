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

# Ton du badge de qualité (couleurs `st.badge`).
DATA_QUALITY_COLORS = {
    "good": "green",
    "partial": "orange",
    "degraded": "red",
    "critical": "red",
}


def site_type_label(site_type: str | None) -> str:
    """Libellé français du type de site (ex. `office` -> `Bureau`)."""
    if not site_type:
        return "Inconnu"
    return SITE_TYPE_LABELS.get(site_type, site_type.capitalize())


def data_quality_label(data_quality: str | None) -> str:
    """Libellé français de la qualité des données (ex. `good` -> `Données fiables`)."""
    if not data_quality:
        return "Qualité inconnue"
    return DATA_QUALITY_LABELS.get(data_quality, data_quality.capitalize())


def data_quality_color(data_quality: str | None) -> str:
    """Couleur du badge de qualité pour `st.badge` (`green`, `orange`, `red`, `gray`)."""
    return DATA_QUALITY_COLORS.get(data_quality, "gray")


def is_data_reliable(data_quality: str | None) -> bool:
    """`True` si la mesure est considérée comme fiable."""
    return data_quality == "good"


def format_number(value: float | None, unit: str = "", decimals: int = 1) -> str:
    """Formate un nombre à la française (virgule décimale), avec unité optionnelle."""
    if value is None:
        return "—"
    formatted = f"{value:.{decimals}f}".replace(".", ",")
    return f"{formatted} {unit}".strip()


def format_power_factor(value: float | None) -> str:
    """Formate le facteur de puissance (ratio sans unité, ex. `0.92`)."""
    if value is None:
        return "—"
    return f"{value:.2f}"


def site_option_label(site: dict) -> str:
    """Libellé d'une option du sélecteur de site : `Nom — Localisation`."""
    name = site.get("site_name") or site.get("site_id") or "Site"
    location = site.get("location")
    return f"{name} — {location}" if location else name


def relative_time(moment: str | datetime | None, *, now: datetime | None = None) -> str:
    """Ancienneté d'une date au format « Il y a … » (français)."""
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
