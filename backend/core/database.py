from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

POSTGRES_DB = os.environ["POSTGRES_DB"]
POSTGRES_APP_USER = os.environ["POSTGRES_APP_USER"]
POSTGRES_APP_PWD = os.environ["POSTGRES_APP_PWD"]

SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_APP_USER}:{POSTGRES_APP_PWD}@postgres:5432/{POSTGRES_DB}"
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()