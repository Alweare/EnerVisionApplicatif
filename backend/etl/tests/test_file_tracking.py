from unittest.mock import MagicMock, Mock

from etl.repository.file_tracking_repository import FileTrackingRepository
from etl.service.file_tracking_service import FileTrackingService


def make_repository_with_rows(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    return FileTrackingRepository(db), db


def test_get_already_processed_returns_empty_set_without_querying():
    repository, db = make_repository_with_rows([])

    assert repository.get_already_processed([]) == set()
    db.query.assert_not_called()


def test_get_already_processed_returns_paths_found_in_database():
    repository, _ = make_repository_with_rows([("brute_data/a.json",)])

    result = repository.get_already_processed(["brute_data/a.json", "brute_data/b.json"])

    assert result == {"brute_data/a.json"}


def test_get_already_processed_splits_large_lists_into_chunks():
    repository, db = make_repository_with_rows([])
    paths = [f"brute_data/{i}.json" for i in range(2500)]

    repository.get_already_processed(paths)

    assert db.query.call_count == 3  # 1000 + 1000 + 500


def test_filter_new_files_keeps_untracked_paths_in_order():
    service = FileTrackingService.__new__(FileTrackingService)
    service.repository = Mock()
    service.repository.get_already_processed.return_value = {"brute_data/b.json"}

    result = service.filter_new_files(
        ["brute_data/a.json", "brute_data/b.json", "brute_data/c.json"]
    )

    assert result == ["brute_data/a.json", "brute_data/c.json"]


def test_mark_processed_delegates_to_repository():
    service = FileTrackingService.__new__(FileTrackingService)
    service.repository = Mock()

    service.mark_processed("brute_data/a.json")

    service.repository.mark_processed.assert_called_once_with("brute_data/a.json")
