from sqlalchemy import Column, Float, String, TIMESTAMP, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID

from shared.base import Base


class Prediction(Base):
    __tablename__ = "prediction"
    __table_args__ = {"schema": "ener"}

    prediction_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_id = Column(String(20), ForeignKey("ener.site.site_id"), nullable=False)
    predicted_for = Column(TIMESTAMP, nullable=True)
    predicted_consumption_kw = Column(Float, nullable=True)
    model_version = Column(String(20), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("now()"))
