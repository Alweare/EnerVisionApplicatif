from sqlalchemy import Column, Float, String, Text, TIMESTAMP, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID

from shared.base import Base


class Recommendation(Base):
    __tablename__ = "recommendation"
    __table_args__ = {"schema": "ener"}

    recommendation_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    prediction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ener.prediction.prediction_id"),
        nullable=False,
    )
    site_id = Column(String(20), ForeignKey("ener.site.site_id"), nullable=True)
    rule_key = Column(String(50), nullable=True)
    action_type = Column(String(30), nullable=True)
    message = Column(Text, nullable=True)
    estimated_gain_kw = Column(Float, nullable=True)
    status = Column(String(15), nullable=False, server_default=text("'pending'"))
    predicted_for = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("now()"))
