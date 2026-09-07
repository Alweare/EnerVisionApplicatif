from sqlalchemy import Column, String, Float, TIMESTAMP, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from shared.base import Base

class Measurement(Base):
    __tablename__ = "measurement"
    __table_args__ = {"schema": "ener"}

    measurement_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_id = Column(String(20), ForeignKey("ener.site.site_id"), nullable=False)
    measurement_date = Column(TIMESTAMP, nullable=False)
    consumption_kw = Column(Float, nullable=True)
    consumption_kwh = Column(Float, nullable=True)
    voltage_v = Column(Float, nullable=True)
    current_a = Column(Float, nullable=True)
    power_factor = Column(Float, nullable=True)
    temperature_celsius = Column(Float, nullable=True)
    humidity_percent = Column(Float, nullable=True)
    null_reason = Column(ARRAY(String), nullable=True)
    forward_filled_fields = Column(ARRAY(String), nullable=True)
    data_quality = Column(String(10), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))