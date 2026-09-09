"""Vérifie le gating d'authentification de l'entrée de l'app."""

from pathlib import Path
from unittest.mock import MagicMock

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _run(monkeypatch, *, logged_in: bool) -> AppTest:
    # Streamlit tourne avec le dossier `frontend/` comme cwd (chemins d'assets relatifs).
    monkeypatch.chdir(Path(APP).parent)

    user = MagicMock()
    user.is_logged_in = logged_in
    user.name = "Test User"
    user.tokens = {"access": "tok"}
    monkeypatch.setattr(st, "user", user)

    at = AppTest.from_file(APP, default_timeout=15)
    at.run()
    return at


def test_login_screen_only_when_not_authenticated(monkeypatch):
    at = _run(monkeypatch, logged_in=False)

    assert [t.value for t in at.title] == ["EnerVision"]
    assert "Se connecter" in [b.label for b in at.button]
    assert "EnerVision — Dashboard" not in [t.value for t in at.title]
    assert at.selectbox == []
    assert not at.exception


def test_no_navigation_menu_when_not_authenticated(monkeypatch):
    at = _run(monkeypatch, logged_in=False)

    assert not any("Dashboard" in str(item) for item in at.sidebar)
