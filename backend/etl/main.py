
import logging
from etl.database import SessionLocal
from etl.service.etl_service import ETLService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    print("Initialisation du script...")

    db = SessionLocal()

    try:
        print("Lancement du service ETL...")
        etl = ETLService(db)
        etl.start_continuous_run(interval=60)
    except KeyboardInterrupt:
        print("\nArrêt manuel du service ETL.")
    except Exception as e:
        print(f"Erreur fatale : {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()