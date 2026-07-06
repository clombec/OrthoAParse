"""
test_orthoadata_mocked.py

Level 2 tests — OrthoADataParse (OrthoAData.py) driven by FakeOrthoAdl instead of a
real Selenium/OrthoAdvance connection.

Each test feeds a canned "input.*" fixture (tests/fixtures/<structure_name>/) through
the real parse*/cleanUp code and checks the result against that structure's
expected.json. Structure names and urls/keys come straight from OrthoABase/urls.yaml
(via the make_parser/urls_config fixtures in conftest.py) — nothing is re-declared here.
"""

import pytest

from OrthoABase.OrthoAdl import OrthoAConnectionError, OrthoADownloadError
from tests.conftest import load_expected, normalize_for_compare


def test_parse_csv_users(make_parser):
    parser = make_parser()
    result = parser.parseCsv("users/recherche", "users")
    assert normalize_for_compare(result) == load_expected("users")


def test_parse_csv_recette_jour(make_parser):
    parser = make_parser()
    result = parser.parseCsv("reglements/history/;search", "recette_jour")
    assert normalize_for_compare(result) == load_expected("recette_jour")


def test_parse_json_metatypes_fauteuils(make_parser):
    parser = make_parser()
    result = parser.parseJson("planning/jt/journees/5/;view?json=1", "MetatypesFauteuils")
    assert normalize_for_compare(result) == load_expected("MetatypesFauteuils")


def test_parse_html_paginated_photos_libelles(make_parser):
    parser = make_parser()
    result = parser.parseHtmlPaginated("medical/photos/libelles", "PhotosLibelles")
    assert normalize_for_compare(result) == load_expected("PhotosLibelles")


def test_download_error_propagates_as_orthoa_download_error(make_parser):
    """A failing download at the OrthoAdl layer must surface as OrthoADownloadError here."""
    parser = make_parser(fail_downloads={"users": OrthoADownloadError("simulated failure")})
    with pytest.raises(OrthoADownloadError):
        parser.parseCsv("users/recherche", "users")


def test_connect_error_propagates_at_construction(make_parser):
    """A failing connect() must prevent OrthoADataParse from being usable at all."""
    with pytest.raises(OrthoAConnectionError):
        make_parser(fail_connect=OrthoAConnectionError("simulated login failure"))
