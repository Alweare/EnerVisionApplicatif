
import logging
import os

from shared.database import SessionLocal
from shared.logging_setup import setup_logging
from etl.service.etl_service import ETLService

setup_logging("etl")
logger = logging.getLogger("etl.main")


def main():
    logger.info("Initialisation du service ETL")

    db = SessionLocal()

    try:
        logger.info("Lancement de la boucle ETL")
        etl = ETLService(db)
        etl.start_continuous_run(
            interval=int(os.getenv("ETL_INTERVAL_SECONDS", "60"))
        )
    except KeyboardInterrupt:
        logger.info("Arrêt manuel du service ETL")
    except Exception:
        logger.exception("Erreur fatale du service ETL")
    finally:
        db.close()


if __name__ == "__main__":
    main()