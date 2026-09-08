from uuid import UUID

from sqlalchemy.orm import Session

from core.api.models.measurement import Measurement
from core.api.models.site import Site
from core.api.models.user import UserSite
from core.api.schemas import SiteRead, SiteWithCurrentRead


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

    def get_by_user(
        self, user_id: UUID, active_only: bool = True
    ) -> list[SiteWithCurrentRead]:
        # Dernière mesure par site (DISTINCT ON = 1 ligne / site, la plus récente).
        latest_measurement = (
            self.db.query(
                Measurement.site_id.label("site_id"),
                Measurement.consumption_kw.label("consumption_kw"),
                Measurement.data_quality.label("data_quality"),
            )
            .distinct(Measurement.site_id)
            .order_by(Measurement.site_id, Measurement.measurement_date.desc())
            .subquery()
        )

        query = (
            self.db.query(
                Site,
                latest_measurement.c.consumption_kw,
                latest_measurement.c.data_quality,
            )
            .join(UserSite, UserSite.site_id == Site.site_id)
            .outerjoin(latest_measurement, latest_measurement.c.site_id == Site.site_id)
            .filter(UserSite.user_id == user_id)
        )
        if active_only:
            query = query.filter(Site.status == "active")

        return [
            SiteWithCurrentRead(
                **SiteRead.model_validate(site).model_dump(),
                current_consumption_kw=consumption_kw,
                data_quality=data_quality,
            )
            for site, consumption_kw, data_quality in query.order_by(Site.site_id).all()
        ]

    def get_by_id(self, site_id: str) -> SiteRead | None:
        row = self.db.query(Site).filter(Site.site_id == site_id).first()
        return SiteRead.model_validate(row) if row is not None else None
