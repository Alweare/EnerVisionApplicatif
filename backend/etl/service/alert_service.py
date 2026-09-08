import logging

from sqlalchemy.orm import Session

from etl.repository.alert_repository import AlertRepository

logger = logging.getLogger(__name__)


REQUIRED_FIELDS = ("alert_id", "site_id")


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AlertRepository(db)

    def build_alert(self, raw: dict) -> dict:
        return {
            "alert_id": raw["alert_id"],
            "site_id": raw["site_id"],
            "severity": raw.get("severity"),
            "type": raw.get("type"),
            "message": raw.get("message"),
            "value": raw.get("value"),
            "threshold": raw.get("threshold"),
            "created_at": raw.get("timestamp"),
        }

    def is_valid(self, raw: dict) -> bool:
        missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
        if missing:
            logger.warning("Alerte ignorée, champs obligatoires manquants : %s", missing)
            return False
        return True

    def save_all(self, alerts: list[dict]) -> int:
        return self.repository.add(alerts)
