"""
Point d'entrée du worker de prédiction.
"""

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info(
        "Worker prediction : boucle d'inférence pas encore branchée "
        "(EN-37 = feature engineering seulement). À implémenter en EN-38 / EN-39."
    )


if __name__ == "__main__":
    main()
