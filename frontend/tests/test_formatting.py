"""Tests de formatting.py — fonctions pures de mise en forme du dashboard."""

from datetime import datetime, timedelta, timezone

import pytest

from formatting import (
    alert_severity_color,
    alert_severity_label,
    alert_type_label,
    alert_counts_by_site_and_type,
    sort_alerts,
    data_quality_color,
    data_quality_label,
    format_number,
    format_power_factor,
    is_data_reliable,
    relative_time,
    site_option_label,
    site_type_label,
)


# --- site_type_label -----------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("office", "Bureau"),
        ("factory", "Usine"),
        ("datacenter", "Data center"),
        ("unknown_type", "Unknown_type"),
        (None, "Inconnu"),
        ("", "Inconnu"),
    ],
)
def test_site_type_label(value, expected):
    assert site_type_label(value) == expected


# --- data_quality_label / color / is_data_reliable -------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("good", "Données fiables"),
        ("partial", "Données partielles"),
        ("degraded", "Données dégradées"),
        ("critical", "Données critiques"),
        ("weird", "Weird"),
        (None, "Qualité inconnue"),
    ],
)
def test_data_quality_label(value, expected):
    assert data_quality_label(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("good", "green"),
        ("partial", "orange"),
        ("degraded", "red"),
        ("critical", "red"),
        ("weird", "gray"),
        (None, "gray"),
    ],
)
def test_data_quality_color(value, expected):
    assert data_quality_color(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("good", True), ("partial", False), ("critical", False), (None, False)],
)
def test_is_data_reliable(value, expected):
    assert is_data_reliable(value) is expected


# --- format_number -----------------------------------------------------

def test_format_number_uses_french_decimal_separator_and_unit():
    assert format_number(87.34, "kW") == "87,3 kW"


def test_format_number_without_unit():
    assert format_number(12.0) == "12,0"


def test_format_number_respects_decimals():
    assert format_number(0.925, decimals=2) == "0,93"


def test_format_number_handles_none():
    assert format_number(None, "kW") == "—"


# --- format_power_factor ---------------------------------------------

def test_format_power_factor_keeps_dot_and_two_decimals():
    assert format_power_factor(0.92) == "0.92"


def test_format_power_factor_handles_none():
    assert format_power_factor(None) == "—"


# --- site_option_label ---------------------------------------------

def test_site_option_label_with_name_and_location():
    site = {"site_name": "Bureau Paris La Défense", "location": "Paris, France"}
    assert site_option_label(site) == "Bureau Paris La Défense — Paris, France"


def test_site_option_label_without_location():
    assert site_option_label({"site_name": "Bureau Paris"}) == "Bureau Paris"


def test_site_option_label_falls_back_to_site_id():
    assert site_option_label({"site_id": "SITE001"}) == "SITE001"


# --- relative_time -----------------------------------------------------

@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=5), "Il y a quelques secondes"),
        (timedelta(seconds=60), "Il y a une minute"),
        (timedelta(minutes=3), "Il y a 3 minutes"),
        (timedelta(hours=1), "Il y a une heure"),
        (timedelta(hours=5), "Il y a 5 heures"),
        (timedelta(days=1), "Il y a un jour"),
        (timedelta(days=4), "Il y a 4 jours"),
    ],
)
def test_relative_time_buckets(delta, expected):
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    assert relative_time(now - delta, now=now) == expected


def test_relative_time_parses_iso_string_without_timezone():
    now = datetime(2026, 9, 6, 12, 1, tzinfo=timezone.utc)
    assert relative_time("2026-09-06T12:00:00", now=now) == "Il y a une minute"


def test_relative_time_parses_iso_string_with_z_suffix():
    now = datetime(2026, 9, 6, 12, 1, tzinfo=timezone.utc)
    assert relative_time("2026-09-06T12:00:00Z", now=now) == "Il y a une minute"


def test_relative_time_handles_none():
    assert relative_time(None) == "Date inconnue"


def test_relative_time_clamps_future_dates():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    future = now + timedelta(minutes=10)
    assert relative_time(future, now=now) == "Il y a quelques secondes"


# --- alertes ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("low", "Faible"),
        ("medium", "Moyenne"),
        ("warning", "Avertissement"),
        ("high", "Élevée"),
        ("critical", "Critique"),
    ],
)
def test_alert_severity_label_translates_known_severities(severity, expected):
    assert alert_severity_label(severity) == expected


def test_alert_severity_label_falls_back_on_unknown_severity():
    assert alert_severity_label("bizarre") == "Bizarre"


def test_alert_severity_label_handles_none():
    assert alert_severity_label(None) == "Gravité inconnue"


@pytest.mark.parametrize(
    ("severity", "expected"),
    [("critical", "red"), ("high", "red"), ("medium", "orange"), ("low", "blue")],
)
def test_alert_severity_color_maps_known_severities(severity, expected):
    assert alert_severity_color(severity) == expected


def test_alert_severity_color_falls_back_to_gray():
    assert alert_severity_color("bizarre") == "gray"
    assert alert_severity_color(None) == "gray"


@pytest.mark.parametrize(
    ("alert_type", "expected"),
    [
        ("spike", "Pic de consommation"),
        ("threshold", "Seuil dépassé"),
        ("anomaly", "Anomalie"),
        ("outage", "Coupure"),
        ("sensor", "Défaillance capteur"),
        ("consumption", "Consommation"),
    ],
)
def test_alert_type_label_translates_known_types(alert_type, expected):
    assert alert_type_label(alert_type) == expected


def test_alert_type_label_falls_back_on_unknown_type():
    assert alert_type_label("bizarre") == "Bizarre"


def test_alert_type_label_handles_none():
    assert alert_type_label(None) == "Type inconnu"


# --- tri des alertes (par date, du plus récent au plus ancien) -------------------------------------------------------

def _alert(alert_id, severity, created_at):
    return {"alert_id": alert_id, "severity": severity, "created_at": created_at}


def test_sort_alerts_by_date_puts_the_most_recent_first():
    vieille = _alert("A", "low", "2026-09-01T10:00:00")
    recente = _alert("B", "critical", "2026-09-07T10:00:00")

    assert sort_alerts([vieille, recente]) == [recente, vieille]


def test_sort_alerts_tolerates_a_missing_date():
    sans_date = {"alert_id": "A", "severity": "low"}
    datee = _alert("B", "low", "2026-09-01T10:00:00")

    assert sort_alerts([sans_date, datee]) == [datee, sans_date]


def test_sort_alerts_returns_a_new_list():
    alerts = [_alert("A", "low", "2026-09-01T10:00:00")]

    assert sort_alerts(alerts) is not alerts


def test_sort_alerts_handles_an_empty_list():
    assert sort_alerts([]) == []


# --- comptage pour l'histogramme -------------------------------------------

SITE_LABELS = {"SITE001": "Bureau Paris", "SITE002": "Usine Lyon"}


def _row(counts, site, type_label):
    return next(c for c in counts if c["site"] == site and c["type"] == type_label)


def test_alert_counts_covers_every_site_and_type():
    counts = alert_counts_by_site_and_type([], SITE_LABELS)

    # 2 sites x 6 types : les histogrammes doivent avoir les mêmes barres.
    assert len(counts) == 2 * 6
    assert all(c["nombre"] == 0 for c in counts)


def test_alert_counts_counts_by_site_and_type():
    alerts = [
        {"site_id": "SITE001", "type": "spike"},
        {"site_id": "SITE001", "type": "spike"},
        {"site_id": "SITE002", "type": "outage"},
    ]

    counts = alert_counts_by_site_and_type(alerts, SITE_LABELS)

    assert _row(counts, "Bureau Paris", "Pic de consommation")["nombre"] == 2
    assert _row(counts, "Usine Lyon", "Coupure")["nombre"] == 1
    assert _row(counts, "Usine Lyon", "Pic de consommation")["nombre"] == 0


def test_alert_counts_ignores_sites_outside_the_filter():
    alerts = [{"site_id": "SITE999", "type": "spike"}]

    counts = alert_counts_by_site_and_type(alerts, SITE_LABELS)

    assert sum(c["nombre"] for c in counts) == 0


def test_alert_counts_ignores_unknown_types():
    alerts = [{"site_id": "SITE001", "type": "bizarre"}, {"site_id": "SITE001"}]

    counts = alert_counts_by_site_and_type(alerts, SITE_LABELS)

    assert sum(c["nombre"] for c in counts) == 0


def test_alert_counts_keeps_the_site_and_type_order_stable():
    counts = alert_counts_by_site_and_type([], SITE_LABELS)

    assert [c["site"] for c in counts[:6]] == ["Bureau Paris"] * 6
    assert counts[0]["type"] == "Pic de consommation"
    assert counts[5]["type"] == "Consommation"
