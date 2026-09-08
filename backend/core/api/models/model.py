from sqlalchemy import Column, String, Float, Boolean, TIMESTAMP, text
from shared.base import Base

class Model(Base):
    __tablename__ = "model"
    __table_args__ = {"schema": "ener"}

    model_version = Column(String(20), primary_key=True)
    algorithm = Column(String(50), nullable=True)
    trained_at = Column(TIMESTAMP, nullable=True)
    mae = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
