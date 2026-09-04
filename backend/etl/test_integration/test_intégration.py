import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.service.etl_service import ETLService
from etl.models.measurement import Measurement
from etl.models.site import Site

load_dotenv()


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

        # 2. Compter le nombre total de mesures avant le traitement
        count_before = db.query(Measurement).count()

        # 3. Lancer le traitement global
        etl.run(limit=15)

        # 4. Compter le nombre total de mesures après le traitement
        count_after = db.query(Measurement).count()

        print(f"Total mesures avant : {count_before} | Total mesures après : {count_after}")

        # 5. Assertion
        assert count_after > count_before, "Le test a échoué : aucune nouvelle donnée n'a été insérée en BDD."
        print("Test d'intégration global réussi avec succès !")

    finally:
        db.close()


if __name__ == "__main__":
    test_etl_integration()