from sqlalchemy.orm import Session

from core.api.models.site import Site
from core.api.models.user import UserSite
from core.api.schemas import SiteRead
from uuid import UUID

class SiteRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists(self, site_id: str) -> bool:
        return (
            self.db.query(Site.site_id).filter(Site.site_id == site_id).first()
            is not None
        )

    def get_all(self) -> list[SiteRead]:
        rows = self.db.query(Site).order_by(Site.site_id).all()
        return [SiteRead.model_validate(row) for row in rows]

    def get_by_user(self, user_id: UUID, active_only: bool = True) -> list[SiteRead]:
        query = (
            self.db.query(Site)
            .join(UserSite, UserSite.site_id == Site.site_id)
            .filter(UserSite.user_id == user_id)
        )
        if active_only:
            query = query.filter(Site.status == "active")
        return [SiteRead.model_validate(row) for row in query.order_by(Site.site_id).all()]

    def get_by_id(self, site_id: str) -> SiteRead | None:
        row = self.db.query(Site).filter(Site.site_id == site_id).first()
        return SiteRead.model_validate(row) if row is not None else None
