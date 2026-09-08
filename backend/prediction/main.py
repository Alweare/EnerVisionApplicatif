"""
Point d'entrée du worker de prédiction.
"""

import logging

from prediction.dataset.dataset import NotEnoughDataError, build_dataset, split_train_test
from prediction.training.training_service import evaluate_model, train_model

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        X_train, X_test, y_train, y_test = split_train_test(build_dataset())
    except NotEnoughDataError as error:
        logger.warning("Entraînement annulé : %s", error)
        return

    model, run_id = train_model(X_train, y_train)
    mae = evaluate_model(model, X_test, y_test, run_id)

    logger.info("Entraînement terminé (run_id=%s, mae=%.4f)", run_id, mae)


if __name__ == "__main__":
    main()
