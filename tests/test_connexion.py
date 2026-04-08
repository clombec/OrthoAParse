"""
test_connexion.py

Pytest tests — verify connection to OrthoAdvance and CSV download,
using real credentials from OrthoABase/config.yaml file.
"""

import os
import pytest
from OrthoABase.OrthoAdl import OrthoAdl, OrthoAConnectionError
import OrthoABase


def test_connexion_orthoadvance(tmp_path):
    """OrthoAdl should connect without raising an exception."""
    adl = OrthoAdl(str(tmp_path))
    assert adl.driver is not None  # the Selenium driver has been created successfully
    adl.end()


def test_download_csv(tmp_path):
    """downloadCsv() should download a CSV file and return its path."""
    adl = OrthoAdl(str(tmp_path))

    csv_path = adl.downloadCsv("statistiques/stat-periodes-traitement")

    assert csv_path is not None                  # a path has been returned
    assert os.path.exists(csv_path)             # the file exists on disk
    assert os.path.getsize(csv_path) > 0        # the file is not empty

    adl.end()

def test_extract_data():
    """extract() should extract data without error."""
    data = OrthoABase.OrthoAData.extract() # Empty request means all urls from urls.yaml
    assert isinstance(data, dict)  # the extracted data should be a dictionary