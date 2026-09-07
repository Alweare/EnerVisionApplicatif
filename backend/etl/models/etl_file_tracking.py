from sqlalchemy import Column, Text, TIMESTAMP, text
from shared.base import Base

class EtlFileTracking(Base):
    __tablename__ = "etl_file_tracking"
    __table_args__ = {"schema": "ener"}

    file_path = Column(Text, primary_key=True)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
