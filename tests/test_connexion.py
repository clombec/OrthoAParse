"""
test_connexion.py

Level 1 tests — real OrthoAdl / OrthoASession against the live OrthoAdvance site,
using real credentials from OrthoABase/config.yaml and the OS keyring.

For the mocked layers (OrthoADataParse, OrthoASession via FakeOrthoAdl), see
test_orthoadata_mocked.py and test_session_mocked.py — those don't need credentials
and run in CI.
"""

import os
import pytest
from OrthoABase.OrthoAdl import OrthoAdl, OrthoAConnectionError
from orthoaget import PROJECT_ROOT
from orthoaget.session import OrthoASession

pytestmark = [
    pytest.mark.real,
    pytest.mark.skipif(
        not os.path.exists(f"{PROJECT_ROOT}/OrthoABase/config.yaml"),
        reason="OrthoABase/config.yaml missing — configure the app before running real tests.",
    ),
]


def test_connexion_orthoadvance(tmp_path):
    """OrthoAdl should connect without raising an exception."""
    adl = OrthoAdl(str(tmp_path))
    try:
        assert adl.driver is not None  # the Selenium driver has been created successfully
    finally:
        adl.end()


def test_download_csv(tmp_path):
    """downloadCsv() should download a CSV file and return its path."""
    adl = OrthoAdl(str(tmp_path))
    try:
        csv_path = adl.downloadCsv("statistiques/stat-periodes-traitement")

        assert csv_path is not None                  # a path has been returned
        assert os.path.exists(csv_path)             # the file exists on disk
        assert os.path.getsize(csv_path) > 0        # the file is not empty
    finally:
        adl.end()

def test_extract_data():
    """OrthoASession.extract() should extract data without error."""
    with OrthoASession() as session:
        data = session.extract(params={'year': "2026"}) # Empty request means all urls from urls.yaml
    assert isinstance(data, dict)

def test_income_records_day():
    """Extracted data should contain expected keys."""
    with OrthoASession() as session:
        data = session.get_income_records(0)
    for line in data:
        print(f"Extracted income records: {line.get('date')}, amount: {line.get('amount')}")
        assert "amount" in line
        assert "date" in line
        assert type(line) == dict
    print(data)
    assert type(data) == list

def test_income_records_5_years():
    """Extracted data should contain expected keys."""
    with OrthoASession() as session:
        data = session.get_income_records(5)
    for line in data:
        print(f"Extracted income records: {line.get('date')}, amount: {line.get('amount')}")
        assert "amount" in line
        assert "date" in line
        assert type(line) == dict
    print(data)
    assert type(data) == list