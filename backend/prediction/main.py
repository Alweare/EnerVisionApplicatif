"""
Point d'entrée du worker de prédiction.
"""

import logging
import os

from prediction.dataset.dataset import NotEnoughDataError, build_dataset, split_train_test
from prediction.dataset.versioning import DatasetVersioningError, version_dataset
from prediction.training.training_service import evaluate_model, train_model

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        df = build_dataset()
        X_train, X_test, y_train, y_test = split_train_test(df)
    except NotEnoughDataError as error:
        logger.warning("Entraînement annulé : %s", error)
        return

    push = os.environ.get("DVC_PUSH", "1") == "1"

    try:
        dvc_hash = version_dataset(df, push=push)
        logger.info("Jeu d'entraînement versionné (dvc_hash=%s)", dvc_hash)
    except DatasetVersioningError as error:
        logger.warning("Versioning DVC échoué, entraînement sans dvc_hash : %s", error)
        dvc_hash = None

    model, run_id = train_model(X_train, y_train, dvc_hash=dvc_hash)
    mae = evaluate_model(model, X_test, y_test, run_id)

    logger.info("Entraînement terminé (run_id=%s, mae=%.4f)", run_id, mae)


if __name__ == "__main__":
    main()
