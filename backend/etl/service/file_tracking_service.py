from sqlalchemy.orm import Session

from etl.repository.file_tracking_repository import FileTrackingRepository


class FileTrackingService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = FileTrackingRepository(db)

# Génère la liste des fichier non-triatés
    def filter_new_files(self, file_paths: list[str]) -> list[str]:
        already_processed = self.repository.get_already_processed(file_paths)
        return [path for path in file_paths if path not in already_processed]

# Marque le fichier comme traité en base de données.
    def mark_processed(self, file_path: str) -> None:
        self.repository.mark_processed(file_path)
