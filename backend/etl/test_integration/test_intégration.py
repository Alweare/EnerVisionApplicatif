import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.models.etl_file_tracking import EtlFileTracking
from etl.service.etl_service import ETLService
from etl.models.measurement import Measurement
from etl.models.site import Site

load_dotenv()

LOOKBACK_MINUTES_TEST = 60 * 24 * 365


def test_etl_integration():
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PWD")
    db_name = os.getenv("POSTGRES_DB")
    host = "localhost"
    port = "5432"

    database_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        site_id_test = "SITE002"  # Assure-toi que cet ID correspond à un site présent dans tes fichiers Azure

        # 1. S'assurer que le site existe en BDD pour que l'ETL ne l'ignore pas
        site_existant = db.query(Site).filter(Site.site_id == site_id_test).first()
        if not site_existant:
            nouveau_site = Site(site_id=site_id_test, site_name="Site Test Integration")
            db.add(nouveau_site)
            db.commit()

        etl = ETLService(db)

        # 2. Compter mesures et fichiers tracés avant le traitement
        count_before = db.query(Measurement).count()
        tracked_before = db.query(EtlFileTracking).count()

        # 3. Premier passage : les fichiers non encore tracés sont ingérés
        etl.run(lookback_minutes=LOOKBACK_MINUTES_TEST)

        count_after = db.query(Measurement).count()
        tracked_after = db.query(EtlFileTracking).count()

        print(f"Total mesures avant : {count_before} | après : {count_after}")
        print(f"Fichiers tracés avant : {tracked_before} | après : {tracked_after}")

        assert tracked_after > tracked_before, (
            "Le test a échoué : aucun fichier n'a été tracé, "
            "le conteneur Azure est-il vide ?"
        )
        assert count_after > count_before, (
            "Le test a échoué : aucune nouvelle donnée n'a été insérée en BDD."
        )

        # 4. Second passage : le dédoublonnage doit tout ignorer (idempotence)
        etl.run(lookback_minutes=LOOKBACK_MINUTES_TEST)

        assert db.query(Measurement).count() == count_after, (
            "Le test a échoué : le second passage a réinséré des mesures."
        )
        assert db.query(EtlFileTracking).count() == tracked_after, (
            "Le test a échoué : le second passage a retracé des fichiers."
        )

        print("Test d'intégration global réussi avec succès !")

    finally:
        db.close()


if __name__ == "__main__":
    test_etl_integration()
