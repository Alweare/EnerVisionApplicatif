import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from prediction.main import main


def _pipeline_result(**overrides):
    base = dict(
        run_id="run-1",
        model_version="1",
        mae=1.0,
        validation_mae=1.0,
        baseline_mae=2.0,
        mae_improvement_vs_baseline=0.5,
        champion_mae=None,
        mae_improvement_vs_champion=None,
        promoted=True,
        reason="ok",
        drift_result=None,
        n_train_rows=10,
        n_validation_rows=2,
        n_test_rows=2,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@patch("prediction.main.run_training_pipeline")
def test_train_command_calls_pipeline_and_returns_zero(mock_pipeline, caplog):
    mock_pipeline.return_value = _pipeline_result()

    with caplog.at_level(logging.INFO):
        exit_code = main(["train"])

    assert exit_code == 0
    mock_pipeline.assert_called_once_with(trigger_source="cli_train")


@patch("prediction.main.run_training_pipeline")
def test_train_command_returns_one_on_failure(mock_pipeline, caplog):
    mock_pipeline.side_effect = RuntimeError("boom")

    with caplog.at_level(logging.INFO):
        exit_code = main(["train"])

    assert exit_code == 1


@patch("prediction.main.train_if_needed")
def test_train_if_needed_command_calls_orchestrator_and_returns_zero(mock_orchestrator, caplog):
    decision = SimpleNamespace(should_retrain=True, reasons=["no_existing_champion"])
    mock_orchestrator.return_value = (decision, _pipeline_result())

    with caplog.at_level(logging.INFO):
        exit_code = main(["train-if-needed"])

    assert exit_code == 0
    mock_orchestrator.assert_called_once_with()


@patch("prediction.main.train_if_needed")
def test_train_if_needed_command_handles_skip(mock_orchestrator, caplog):
    decision = SimpleNamespace(should_retrain=False, reasons=[])
    mock_orchestrator.return_value = (decision, None)

    with caplog.at_level(logging.INFO):
        exit_code = main(["train-if-needed"])

    assert exit_code == 0


@patch("prediction.main.train_if_needed")
def test_train_if_needed_command_returns_one_on_failure(mock_orchestrator, caplog):
    mock_orchestrator.side_effect = RuntimeError("boom")

    with caplog.at_level(logging.INFO):
        exit_code = main(["train-if-needed"])

    assert exit_code == 1


def test_main_requires_a_command():
    with pytest.raises(SystemExit):
        main([])


@patch("uvicorn.run")
def test_serve_command_runs_uvicorn_on_the_api_app(mock_run, monkeypatch):
    monkeypatch.delenv("PREDICTION_HOST", raising=False)

    exit_code = main(["serve"])

    assert exit_code == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == "prediction.api.app:app"
    # Défaut sûr : boucle locale quand PREDICTION_HOST n'est pas fourni.
    assert kwargs["host"] == "127.0.0.1"


@patch("uvicorn.run")
def test_serve_command_binds_host_from_environment(mock_run, monkeypatch):
    # En conteneur, le Dockerfile pose PREDICTION_HOST=0.0.0.0 : l'hôte doit
    # être repris tel quel pour rester joignable.
    monkeypatch.setenv("PREDICTION_HOST", "0.0.0.0")

    exit_code = main(["serve"])

    assert exit_code == 0
    _args, kwargs = mock_run.call_args
    assert kwargs["host"] == "0.0.0.0"
