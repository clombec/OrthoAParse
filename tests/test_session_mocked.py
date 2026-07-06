"""
test_session_mocked.py

Level 3 tests — OrthoASession driven by FakeOrthoAdl via OrthoASession(test_mode=True).
This is the entry point higher layers (Flask apps in OrthoAProthData/OrthoARecettes,
scripts...) should use to test against OrthoASession without a real Selenium/OrthoAdvance
connection — callers never need to know FakeOrthoAdl exists, and never pass a fixtures
directory or a users_db.json path (those are fixed constants in tests/fakes/fake_orthoadl.py).

Note: html_form endpoints (acte_form / fetch_act / confirm_act_done) drive the Selenium
driver directly (driver.get / driver.page_source) rather than going through
OrthoAdl.downloadPage*, so they are not covered by FakeOrthoAdl yet — a richer fake
driver would be needed for those.
"""

import pytest

from OrthoABase.OrthoAdl import OrthoAConnectionError, OrthoADownloadError
from tests.conftest import load_expected, normalize_for_compare


def test_get_users_list(make_session):
    with make_session() as session:
        users = session.get_users_list()
    assert normalize_for_compare(users) == load_expected("users")


def test_get_income_records(make_session):
    with make_session() as session:
        data = session.get_income_records()
    assert normalize_for_compare(data) == load_expected("recette_jour")


def test_extract_unknown_entry_raises_keyerror(make_session):
    with make_session() as session:
        with pytest.raises(KeyError):
            session.extract(["not_a_real_structure"])


def test_connection_failure_propagates(make_session):
    with pytest.raises(OrthoAConnectionError):
        make_session(fail_connect=OrthoAConnectionError("simulated login failure"))


def test_download_failure_propagates_through_session(make_session):
    with make_session(fail_downloads={"users": OrthoADownloadError("simulated failure")}) as session:
        with pytest.raises(OrthoADownloadError):
            session.get_users_list()
