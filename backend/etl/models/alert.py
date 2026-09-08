from sqlalchemy import Column, String, Float, Text, TIMESTAMP, ForeignKey, text
from shared.base import Base

class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = {"schema": "ener"}

    alert_id = Column(String(50), primary_key=True)
    site_id = Column(String(20), ForeignKey("ener.site.site_id"), nullable=False)
    severity = Column(String(10), nullable=True)
    type = Column(String(15), nullable=True)
    message = Column(Text, nullable=True)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("now()"))
