import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

POSTGRES_DB = os.environ["POSTGRES_DB"]
POSTGRES_APP_USER = os.environ["POSTGRES_APP_USER"]
POSTGRES_APP_PWD = os.environ["POSTGRES_APP_PWD"]

SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_APP_USER}:{POSTGRES_APP_PWD}@postgres:5432/{POSTGRES_DB}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()