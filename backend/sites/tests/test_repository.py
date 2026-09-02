from backend.sites.repository import get_site, list_sites
from backend.sites.schemas import Site


def test_list_sites_returns_all_mock_sites():
    sites = list_sites()

    assert len(sites) == 3
    assert all(isinstance(site, Site) for site in sites)
    assert [site.site_id for site in sites] == ["SITE001", "SITE002", "SITE003"]


def test_get_site_returns_matching_site():
    site = get_site("SITE002")

    assert site is not None
    assert site.site_id == "SITE002"
    assert site.site_name == "Usine Lyon Vénissieux"


def test_get_site_returns_none_when_unknown():
    assert get_site("UNKNOWN") is None
