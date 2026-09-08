import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from etl.service.alert_service import AlertService
from etl.service.etl_service import DEFAULT_LOOKBACK_MINUTES, ETLService

def make_service_with_mock():
    service = ETLService.__new__(ETLService)
    service.measurement_service = Mock()
    service.file_tracking_service = Mock()
    service.container_client = Mock()
    service.db = Mock()
    service.db.begin_nested.return_value.__enter__ = Mock()
    service.db.begin_nested.return_value.__exit__ = Mock(return_value=False)
    service.measurement_service.measurement_exists.return_value = False
    service.lookback_minutes = DEFAULT_LOOKBACK_MINUTES
    service.forward_fill_depth = 3
    return service

def make_blob(name, minutes_ago):
    return SimpleNamespace(
        name=name,
        last_modified=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )

def test_forward_fill_returns_unchanged_when_nothing_missing():
    service = make_service_with_mock()
    reading = {
        "consumption_kw": 87.34, "consumption_kwh": 87.34, "voltage_v": 401.2,
        "current_a": 132.5, "power_factor": 0.923, "temperature_celsius": 22.1,
        "humidity_percent": 58.4,
    }

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned == {**reading, "forward_filled_fields": []}
    service.measurement_service.get_last_measurements.assert_not_called()

def test_forward_fill_fills_missing_field_from_last_measurement():
    service = make_service_with_mock()
    last = Mock(temperature_celsius=20.0, humidity_percent=50.0,
                forward_filled_fields=[])
    service.measurement_service.get_last_measurements.return_value = [last]

    reading = {
        "consumption_kw": 87.34, "consumption_kwh": 87.34, "voltage_v": 401.2,
        "current_a": 132.5, "power_factor": 0.923,
        "temperature_celsius": None, "humidity_percent": None,
    }

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned["temperature_celsius"] == 20.0
    assert cleaned["humidity_percent"] == 50.0
    assert cleaned["consumption_kw"] == 87.34

def test_forward_fill_keeps_null_when_no_previous_measurement():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = []

    reading = {"consumption_kw": 87.34, "temperature_celsius": None}

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned["temperature_celsius"] is None

def test_forward_fill_does_not_mutate_original_reading():
    service = make_service_with_mock()
    last = Mock(temperature_celsius=20.0, forward_filled_fields=[])
    service.measurement_service.get_last_measurements.return_value = [last]

    reading = {"consumption_kw": 87.34, "temperature_celsius": None}
    service.forward_fill("SITE001", reading)

    assert reading["temperature_celsius"] is None  # original has not change

def test_transform_builds_measurement_from_cleaned_reading():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = []
    expected_measurement = Mock()
    service.measurement_service.build_measurement.return_value = expected_measurement

    reading = {"consumption_kw": 87.34, "timestamp": datetime.now()}
    result = service.transform("SITE001", reading)

    assert result is expected_measurement
    service.measurement_service.build_measurement.assert_called_once()

def test_load_adds_measurement_without_commit():
    service = make_service_with_mock()
    measurement = Mock()

    service.load(measurement)

    service.measurement_service.add_measurement.assert_called_once_with(measurement)
    service.db.commit.assert_not_called()


# --- Étape 2 : filtrage temporel sur last_modified ------------------------

def test_list_recent_blob_paths_keeps_only_blobs_within_window():
    service = make_service_with_mock()
    service.lookback_minutes = 3
    service.container_client.list_blobs.return_value = [
        make_blob("measures/old.json", minutes_ago=10),
        make_blob("measures/recent.json", minutes_ago=1),
    ]

    paths = service.list_recent_blob_paths()

    assert paths == ["measures/recent.json"]
    service.container_client.list_blobs.assert_called_once_with(
        name_starts_with=f"measures/{datetime.now(timezone.utc):%Y/%m/%d}/"
    )

def test_list_recent_blob_paths_sorts_chronologically():
    service = make_service_with_mock()
    service.lookback_minutes = 3
    service.container_client.list_blobs.return_value = [
        make_blob("measures/b.json", minutes_ago=1),
        make_blob("measures/a.json", minutes_ago=2),
    ]

    paths = service.list_recent_blob_paths()

    assert paths == ["measures/a.json", "measures/b.json"]

def test_list_recent_blob_paths_uses_explicit_window_over_default():
    service = make_service_with_mock()
    service.lookback_minutes = 3
    service.container_client.list_blobs.return_value = [
        make_blob("measures/old.json", minutes_ago=30),
    ]

    assert service.list_recent_blob_paths() == []
    assert service.list_recent_blob_paths(lookback_minutes=60) == ["measures/old.json"]


# --- Étape 3 : dédoublonnage ---------------------------------------------

def test_run_processes_only_files_not_already_tracked():
    service = make_service_with_mock()
    service.list_recent_blob_paths = Mock(
        return_value=["measures/a.json", "measures/b.json"]
    )
    service.file_tracking_service.filter_new_files.return_value = ["measures/b.json"]
    service.process_batch = Mock()

    service.run()

    service.file_tracking_service.filter_new_files.assert_called_once_with(
        ["measures/a.json", "measures/b.json"]
    )
    service.process_batch.assert_called_once_with(["measures/b.json"])

def test_run_does_nothing_when_no_recent_file():
    service = make_service_with_mock()
    service.list_recent_blob_paths = Mock(return_value=[])
    service.process_batch = Mock()

    service.run()

    service.process_batch.assert_not_called()
    service.file_tracking_service.filter_new_files.assert_not_called()


# --- Étape 4 : insertion transactionnelle --------------------------------

def test_process_batch_commits_once_for_all_files():
    service = make_service_with_mock()
    service.download_readings = Mock(side_effect=lambda path: [
        {"site_id": "SITE001", "reading": path}
    ])
    measurements = {
        "measures/a.json": Mock(site_id="SITE001", measurement_date=1),
        "measures/b.json": Mock(site_id="SITE001", measurement_date=2),
    }
    service.transform = Mock(side_effect=lambda site_id, reading: measurements[reading["reading"]])
    service.load = Mock()

    assert service.process_batch(["measures/a.json", "measures/b.json"]) is True

    assert service.load.call_count == 2
    service.load.assert_any_call(measurements["measures/a.json"])
    service.load.assert_any_call(measurements["measures/b.json"])

def test_process_batch_rolls_back_everything_when_commit_fails():
    service = make_service_with_mock()
    service.download_readings = Mock(return_value=[{"site_id": "SITE001"}])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock(return_value="measurement")
    service.load = Mock()
    service.db.commit.side_effect = SQLAlchemyError("connexion perdue")

    assert service.process_batch(["measures/a.json"]) is False

    service.db.rollback.assert_called_once()

def test_process_batch_skips_failing_file_and_keeps_the_rest():
    service = make_service_with_mock()
    service.download_readings = Mock(side_effect=[
        OSError("azure indisponible"),
        [{"site_id": "SITE001", "reading": "ok"}],
    ])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock(return_value=Mock(site_id="SITE001", measurement_date=1))
    service.load = Mock()

    assert service.process_batch(["measures/ko.json", "measures/ok.json"]) is True

    service.file_tracking_service.mark_processed.assert_called_once_with("measures/ok.json")
    service.db.commit.assert_called_once()

def test_stage_blob_skips_reading_without_site_id_but_still_tracks_file():
    service = make_service_with_mock()
    service.download_readings = Mock(return_value=[{"consumption_kw": 12.0}])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock()
    service.load = Mock()

    assert service.stage_blob("measures/a.json") == 0

    service.transform.assert_not_called()
    service.load.assert_not_called()

def test_start_continuous_run_loops_then_stops(monkeypatch):
    service = make_service_with_mock()
    service.run = Mock()

    calls = {"n": 0}
    def fake_sleep(_interval):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt
    monkeypatch.setattr("etl.service.etl_service.time.sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        service.start_continuous_run(interval=0)

    assert service.run.call_count == 2

def test_start_continuous_run_logs_error_and_keeps_going(monkeypatch):
    service = make_service_with_mock()
    service.run = Mock(side_effect=RuntimeError("boom"))

    def fake_sleep(_interval):
        raise KeyboardInterrupt
    monkeypatch.setattr("etl.service.etl_service.time.sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        service.start_continuous_run(interval=0)

    service.run.assert_called_once()


# --- Forward-fill borné à 3 enregistrements --------------------------------

def measurement_with(**fields):
    """Mesure factice : tout champ non précisé vaut None."""
    values = {f: None for f in (
        "consumption_kw", "consumption_kwh", "voltage_v", "current_a",
        "power_factor", "temperature_celsius", "humidity_percent",
    )}
    values["forward_filled_fields"] = []
    values.update(fields)
    return SimpleNamespace(**values)


def test_forward_fill_looks_back_at_three_records_only():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = []

    service.forward_fill("SITE001", {"temperature_celsius": None})

    service.measurement_service.get_last_measurements.assert_called_once_with(
        "SITE001", 3
    )


def test_forward_fill_takes_the_most_recent_non_null_of_the_three():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=21.0),
        measurement_with(temperature_celsius=19.0),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] == 21.0


def test_forward_fill_keeps_null_when_the_three_records_are_all_null():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=None),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] is None


def test_forward_fill_no_longer_copies_a_null_from_the_last_record():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(voltage_v=None),
        measurement_with(voltage_v=400.0),
    ]

    cleaned = service.forward_fill("SITE001", {"voltage_v": None})

    assert cleaned["voltage_v"] == 400.0


def test_forward_fill_resolves_each_field_independently():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(voltage_v=401.2, temperature_celsius=None),
        measurement_with(voltage_v=None, temperature_celsius=22.1),
    ]

    cleaned = service.forward_fill(
        "SITE001", {"voltage_v": None, "temperature_celsius": None}
    )

    assert cleaned["voltage_v"] == 401.2
    assert cleaned["temperature_celsius"] == 22.1


def test_forward_fill_warns_about_fields_left_null(caplog):
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=None),
    ]

    with caplog.at_level(logging.WARNING, logger="etl.service.etl_service"):
        service.forward_fill("SITE001", {"temperature_celsius": None})

    assert any("restent null" in r.getMessage() for r in caplog.records)


def test_forward_fill_depth_defaults_to_three():
    from etl.service.etl_service import DEFAULT_FORWARD_FILL_DEPTH

    assert DEFAULT_FORWARD_FILL_DEPTH == 3


# --- Plafond de recopies consécutives --------------------------------------

def test_forward_fill_stops_after_three_consecutive_copies():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] is None
    assert cleaned["forward_filled_fields"] == []


def test_forward_fill_still_copies_at_the_third_time():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0),  # mesure réelle
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] == 22.0
    assert cleaned["forward_filled_fields"] == ["temperature_celsius"]


def test_a_real_measurement_resets_the_streak():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=25.0),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] == 25.0


def test_the_streak_is_counted_per_field():
    service = make_service_with_mock()
    recents = [
        measurement_with(temperature_celsius=22.0, voltage_v=400.0,
                         forward_filled_fields=["temperature_celsius"]),
    ] * 3
    service.measurement_service.get_last_measurements.return_value = recents

    cleaned = service.forward_fill(
        "SITE001", {"temperature_celsius": None, "voltage_v": None}
    )

    assert cleaned["temperature_celsius"] is None
    assert cleaned["voltage_v"] == 400.0
    assert cleaned["forward_filled_fields"] == ["voltage_v"]


def test_forward_fill_records_which_fields_it_filled():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(voltage_v=401.2, temperature_celsius=22.1),
    ]

    cleaned = service.forward_fill(
        "SITE001", {"voltage_v": None, "temperature_celsius": None}
    )

    assert set(cleaned["forward_filled_fields"]) == {"voltage_v", "temperature_celsius"}


def test_forward_fill_records_nothing_when_no_field_is_missing():
    service = make_service_with_mock()
    complete = {
        "consumption_kw": 87.34, "consumption_kwh": 87.34, "voltage_v": 401.2,
        "current_a": 132.5, "power_factor": 0.923, "temperature_celsius": 22.1,
        "humidity_percent": 58.4,
    }

    cleaned = service.forward_fill("SITE001", complete)

    assert cleaned["forward_filled_fields"] == []
    service.measurement_service.get_last_measurements.assert_not_called()


def test_a_null_record_does_not_restart_the_copies():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] is None


def test_copies_resume_after_the_sensor_comes_back():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurements.return_value = [
        measurement_with(temperature_celsius=25.0),
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=None),
    ]

    cleaned = service.forward_fill("SITE001", {"temperature_celsius": None})

    assert cleaned["temperature_celsius"] == 25.0
    assert cleaned["forward_filled_fields"] == ["temperature_celsius"]


def test_both_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("ETL_LOOKBACK_MINUTES", "17")
    monkeypatch.setenv("ETL_FORWARD_FILL_DEPTH", "5")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "compte")
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "raw")
    monkeypatch.setenv("AZURE_SAS_ETL", "jeton")

    service = ETLService(Mock())

    assert service.lookback_minutes == 17
    assert service.forward_fill_depth == 5


def test_the_configured_depth_drives_the_lookup(monkeypatch):
    service = make_service_with_mock()
    service.forward_fill_depth = 5
    service.measurement_service.get_last_measurements.return_value = []

    service.forward_fill("SITE001", {"temperature_celsius": None})

    service.measurement_service.get_last_measurements.assert_called_once_with(
        "SITE001", 5
    )


def test_cycles_since_real_value_counts_until_a_real_measurement():
    from etl.service.etl_service import cycles_since_real_value

    recents = [
        measurement_with(temperature_celsius=22.0,
                         forward_filled_fields=["temperature_celsius"]),
        measurement_with(temperature_celsius=None),
        measurement_with(temperature_celsius=22.0),
    ]

    assert cycles_since_real_value("temperature_celsius", recents) == 2


def test_cycles_since_real_value_is_zero_on_a_fresh_measurement():
    from etl.service.etl_service import cycles_since_real_value

    recents = [measurement_with(temperature_celsius=22.0)]

    assert cycles_since_real_value("temperature_celsius", recents) == 0


# --- Alertes (apporté par EN-278) ------------------------------------------

def make_alert_service_with_mock(known_sites=("SITE001", "SITE002")):
    service = ETLService.__new__(ETLService)
    service.db = Mock()
    service.db.query.return_value.all.return_value = [(s,) for s in known_sites]
    service.db.begin_nested.return_value.__enter__ = Mock()
    service.db.begin_nested.return_value.__exit__ = Mock(return_value=False)
    service.alert_service = AlertService.__new__(AlertService)
    service.alert_service.repository = Mock()
    service.alert_service.repository.add.side_effect = len
    service.file_tracking_service = Mock()
    service.file_tracking_service.filter_new_files.side_effect = lambda paths: paths
    return service


RAW_ALERT = {
    "alert_id": "ALR-SITE002-1718458320",
    "timestamp": "2024-06-15T14:12:00",
    "site_id": "SITE002",
    "severity": "critical",
    "type": "outage",
    "message": "Risque de surcharge sur Usine Lyon Vénissieux",
    "value": 812.5,
    "threshold": 720.0,
}


def test_stage_alert_blob_inserts_and_tracks_the_file():
    service = make_alert_service_with_mock()
    service.download_alerts = Mock(return_value=[RAW_ALERT])

    assert service.stage_alert_blob("alert/a.json") == 1

    service.file_tracking_service.mark_processed.assert_called_once_with("alert/a.json")
    service.db.commit.assert_not_called()


def test_stage_alert_blob_skips_alerts_of_unknown_sites():
    service = make_alert_service_with_mock(known_sites=("SITE001",))
    service.download_alerts = Mock(return_value=[RAW_ALERT])  # SITE002 inconnu

    assert service.stage_alert_blob("alert/a.json") == 0
    assert service.alert_service.repository.add.call_args[0][0] == []


def test_stage_alert_blob_skips_alerts_without_an_id():
    service = make_alert_service_with_mock()
    incomplete = {k: v for k, v in RAW_ALERT.items() if k != "alert_id"}
    service.download_alerts = Mock(return_value=[incomplete])

    assert service.stage_alert_blob("alert/a.json") == 0


def test_run_alerts_processes_each_new_blob_then_commits_once():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(
        return_value=["alert/a.json", "alert/b.json"]
    )
    service.stage_alert_blob = Mock(return_value=1)

    assert service.run_alerts() == 2
    assert service.stage_alert_blob.call_count == 2
    service.db.commit.assert_called_once()


def test_run_alerts_ignores_blobs_already_tracked():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(
        return_value=["alert/vu.json", "alert/neuf.json"]
    )
    service.file_tracking_service.filter_new_files.side_effect = None
    service.file_tracking_service.filter_new_files.return_value = ["alert/neuf.json"]
    service.stage_alert_blob = Mock(return_value=1)

    assert service.run_alerts() == 1
    service.stage_alert_blob.assert_called_once_with("alert/neuf.json")


def test_run_alerts_skips_a_failing_blob_and_keeps_the_others():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(return_value=["alert/ko.json", "alert/ok.json"])
    service.stage_alert_blob = Mock(side_effect=[ValueError("json invalide"), 1])

    assert service.run_alerts() == 1
    service.db.commit.assert_called_once()


def test_run_alerts_does_nothing_when_every_blob_is_tracked():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(return_value=["alert/vu.json"])
    service.file_tracking_service.filter_new_files.side_effect = None
    service.file_tracking_service.filter_new_files.return_value = []
    service.stage_alert_blob = Mock()

    assert service.run_alerts() == 0
    service.stage_alert_blob.assert_not_called()
    service.db.commit.assert_not_called()


def test_list_recent_alert_blobs_ignores_blobs_outside_the_window(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "raw")
    service = ETLService.__new__(ETLService)

    service.lookback_minutes = 10
    now = datetime.now(timezone.utc)
    day = f"{now:%Y/%m/%d}"
    container_client = Mock()
    container_client.list_blobs.return_value = [
        SimpleNamespace(
            name=f"alert/{day}/vieux.json", last_modified=now - timedelta(days=3)
        ),
        SimpleNamespace(
            name=f"alert/{day}/recent.json", last_modified=now - timedelta(minutes=5)
        ),
    ]
    service.container_client = container_client

    assert service.list_recent_alert_blobs() == [f"alert/{day}/recent.json"]
    # Comme les mesures : seuls les jours de la fenêtre sont listés.
    container_client.list_blobs.assert_called_once_with(
        name_starts_with=f"alert/{day}/"
    )


def test_download_alerts_accepts_a_list_or_a_single_object(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "raw")
    service = ETLService.__new__(ETLService)
    container_client = Mock()

    def blob_returning(payload):
        client = Mock()
        client.download_blob.return_value.readall.return_value = json.dumps(payload).encode()
        return client

    service.container_client = container_client

    container_client.get_blob_client.return_value = blob_returning([RAW_ALERT])
    assert service.download_alerts("alert/a.json") == [RAW_ALERT]

    container_client.get_blob_client.return_value = blob_returning(RAW_ALERT)
    assert service.download_alerts("alert/a.json") == [RAW_ALERT]
