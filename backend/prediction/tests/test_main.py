import logging
from unittest.mock import patch

from backend.prediction.main import main


@patch("backend.prediction.main.evaluate_model")
@patch("backend.prediction.main.train_model")
@patch("backend.prediction.main.split_train_test")
@patch("backend.prediction.main.build_dataset")
def test_main_runs_without_error(
    mock_build_dataset,
    mock_split_train_test,
    mock_train_model,
    mock_evaluate_model,
    caplog,
):
    mock_build_dataset.return_value = "dataset"

    mock_split_train_test.return_value = (
        "X_train",
        "X_test",
        "y_train",
        "y_test",
    )

    mock_train_model.return_value = (
        "model",
        "run-id-123",
    )

    mock_evaluate_model.return_value = 10.5

    with caplog.at_level(logging.INFO):
        main()

    mock_build_dataset.assert_called_once()

    mock_split_train_test.assert_called_once_with(
        "dataset"
    )

    mock_train_model.assert_called_once()

    mock_evaluate_model.assert_called_once_with(
        "model",
        "X_test",
        "y_test",
        "run-id-123",
    )