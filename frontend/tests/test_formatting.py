"""Tests de formatting.py — fonctions pures de mise en forme du dashboard."""

from datetime import datetime, timedelta, timezone

import pytest

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
