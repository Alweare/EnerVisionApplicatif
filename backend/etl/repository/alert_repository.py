from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from etl.models.alert import Alert


class AlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, alerts: list[dict]) -> int:
        if not alerts:
            return 0

        statement = (
            insert(Alert.__table__)
            .values(alerts)
            .on_conflict_do_nothing(index_elements=[Alert.alert_id])
        )
        return self.db.execute(statement).rowcount
