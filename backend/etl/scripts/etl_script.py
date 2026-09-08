import argparse
import logging
import os
from dotenv import load_dotenv

from shared.database import SessionLocal
from etl.service.etl_service import ETLService

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DAYS_BACK = int(os.getenv("SEED_DAYS_BACK"))

def run(days_back: int = DAYS_BACK) -> None:
    lookback_minutes = days_back * 24 * 60

    db = SessionLocal()
    try:
        logger.info("--- Début du nettoyage historique (%d jour(s)) ---", days_back)
        service = ETLService(db)
        service.run(lookback_minutes=lookback_minutes)
        logger.info("=== FIN DU NETTOYAGE ===")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Nettoie et charge en base l'historique brut déposé sur Azure Blob."
    )
    parser.add_argument(
        "--days-back", type=int, default=DAYS_BACK,
        help="Nombre de jours à couvrir en arrière (défaut : DAYS_BACK, cohérent avec HistoricalDataSeeder)",
    )
    args = parser.parse_args()

    run(days_back=args.days_back)


if __name__ == "__main__":
    main()