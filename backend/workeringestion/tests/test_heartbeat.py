"""Tests du battement de cœur sur disque partagé (shared.heartbeat).

Le worker et l'ETL n'ayant pas de port HTTP, leur healthcheck Docker repose
entièrement sur la fraîcheur de ce fichier : on vérifie ici l'écriture, la
fenêtre de fraîcheur et le cas où le fichier n'existe pas encore.
"""

import time

import pytest

from shared import heartbeat


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    chemin = tmp_path / "heartbeat"
    monkeypatch.setattr(heartbeat, "CHEMIN", chemin)
    return chemin


def test_touch_ecrit_un_horodatage(heartbeat_file):
    heartbeat.touch()

    assert heartbeat_file.exists()
    assert float(heartbeat_file.read_text()) == pytest.approx(time.time(), abs=5)


def test_est_frais_vrai_juste_apres_touch(heartbeat_file):
    heartbeat.touch()

    assert heartbeat.est_frais(age_max_secondes=60) is True


def test_est_frais_faux_si_fichier_trop_vieux(heartbeat_file):
    heartbeat.touch()
    # Recule la date de modification bien au-delà de la fenêtre autorisée.
    vieux = time.time() - 3600
    import os

    os.utime(heartbeat_file, (vieux, vieux))

    assert heartbeat.est_frais(age_max_secondes=300) is False


def test_est_frais_faux_si_fichier_absent(heartbeat_file):
    assert not heartbeat_file.exists()

    assert heartbeat.est_frais(age_max_secondes=300) is False
