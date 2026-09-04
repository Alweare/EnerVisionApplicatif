from unittest.mock import Mock

import pytest

from core.api.schemas import SiteRead
from core.api.service.site_service import SiteNotFoundError, SiteService


@pytest.fixture
def site_service():
    service = SiteService.__new__(SiteService)
    service.repository = Mock()
    return service


def _site(site_id: str = "SITE001") -> SiteRead:
    return SiteRead(
        site_id=site_id,
        site_type="office",
        site_name="Bureau Paris",
        location="Paris, France",
        capacity_kw=200.0,
        status="active",
    )


# --- list_sites -----------------------------------------------------------

def test_list_sites_returns_repository_result(site_service):
    sites = [_site("SITE001"), _site("SITE002")]
    site_service.repository.get_all.return_value = sites

    result = site_service.list_sites()

    assert result == sites
    assert all(isinstance(s, SiteRead) for s in result)
    site_service.repository.get_all.assert_called_once_with()


def test_list_sites_returns_empty_list_when_no_site(site_service):
    site_service.repository.get_all.return_value = []

    assert site_service.list_sites() == []


# --- get_site -----------------------------------------------------------

def test_get_site_returns_matching_site(site_service):
    site = _site("SITE001")
    site_service.repository.get_by_id.return_value = site

    result = site_service.get_site("SITE001")

    assert result is site
    site_service.repository.get_by_id.assert_called_once_with("SITE001")


def test_get_site_raises_when_site_unknown(site_service):
    site_service.repository.get_by_id.return_value = None

    with pytest.raises(SiteNotFoundError) as error:
        site_service.get_site("SITE999")

    assert error.value.site_id == "SITE999"
