from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from shared.base import Base

class UserSite(Base):
    __tablename__ = "user_site"
    __table_args__ = {"schema": "ener"}

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    site_id = Column(String(50), primary_key=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))