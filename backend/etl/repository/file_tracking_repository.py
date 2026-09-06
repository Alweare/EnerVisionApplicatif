from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from etl.models.etl_file_tracking import EtlFileTracking

CHUNK_SIZE = 1000


class FileTrackingRepository:
    def __init__(self, db: Session):
        self.db = db

# Renvoie la liste des fichiers déjà traités en base de données (table etl_file_tracking)
    def get_already_processed(self, file_paths: list[str]) -> set[str]:
        if not file_paths:
            return set()

        already_processed: set[str] = set()
        for start in range(0, len(file_paths), CHUNK_SIZE):
            chunk = file_paths[start:start + CHUNK_SIZE]
            rows = (
                self.db.query(EtlFileTracking.file_path)
                .filter(EtlFileTracking.file_path.in_(chunk))
                .all()
            )
            already_processed.update(row[0] for row in rows)

        return already_processed

# Insère le nom du fichier traité en base de données.
    def mark_processed(self, file_path: str) -> None:
        statement = (
            insert(EtlFileTracking.__table__)
            .values(file_path=file_path)
            .on_conflict_do_nothing(index_elements=[EtlFileTracking.file_path])
        )
        self.db.execute(statement)
