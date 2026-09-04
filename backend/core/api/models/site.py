from sqlalchemy import Column, String, Float
from core.base import Base

class Site(Base):
    __tablename__ = "site"
    __table_args__ = {"schema": "ener"}

    site_id = Column(String(20), primary_key=True)
    site_type = Column(String(10))
    site_name = Column(String(50))
    location = Column(String(30))
    capacity_kw = Column(Float)
    status = Column(String(10))