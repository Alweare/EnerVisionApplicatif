from sqlalchemy.orm import Session

from core.api.models.model import Model
from core.api.schemas import ModelInfo


class ModelRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_version(self, model_version: str) -> ModelInfo | None:
        row = (
            self.db.query(Model)
            .filter(Model.model_version == model_version)
            .first()
        )
        return ModelInfo.model_validate(row) if row is not None else None

    def get_active(self) -> ModelInfo | None:
        row = self.db.query(Model).filter(Model.is_active.is_(True)).first()
        return ModelInfo.model_validate(row) if row is not None else None
