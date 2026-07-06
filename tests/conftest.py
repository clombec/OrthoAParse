import json
from pathlib import Path

import pytest
import yaml

from OrthoABase.OrthoAData import OrthoADataParse
from tests.fakes.fake_orthoadl import FIXTURES_ROOT
from tests.fakes.test_config import CONFIG

URLS_FILE = Path(__file__).parent.parent / "OrthoABase" / "urls.yaml"


@pytest.fixture(scope="session")
def urls_config() -> dict:
    """The real OrthoABase/urls.yaml — reused as-is instead of re-declaring urls/keys in tests."""
    with open(URLS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(autouse=True)
def _reset_fake_orthoadl_config():
    """Guarantee fail_connect/fail_downloads never leak from one test to the next."""
    yield
    CONFIG.reset()


def load_expected(structure_name: str):
    """Load tests/fixtures/<structure_name>/expected.json."""
    path = FIXTURES_ROOT / structure_name / "expected.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_for_compare(value):
    """
    Round-trip through JSON so results can be compared to an expected.json fixture
    regardless of Python-only details: non-string dict keys (int, ...) are stringified
    the same way json.dumps would, and non-serializable values (date, datetime, numpy
    scalars, ...) fall back to str().
    """
    return json.loads(json.dumps(value, default=str))


@pytest.fixture
def make_parser(tmp_path, urls_config):
    """
    Build an OrthoADataParse(test_mode=True), backed by FakeOrthoAdl and wired to
    tests/fixtures and the real urls.yaml. Pass fail_connect / fail_downloads to
    simulate error paths.

    Usage:
        parser = make_parser()
        parser = make_parser(fail_downloads={"users": OrthoAdl.OrthoADownloadError("boom")})
    """
    def _make(fail_connect=None, fail_downloads=None):
        CONFIG.fail_connect = fail_connect
        CONFIG.fail_downloads = fail_downloads or {}
        parser = OrthoADataParse(str(tmp_path), test_mode=True)
        parser.urlsConfig = urls_config
        return parser

    return _make


@pytest.fixture
def make_session():
    """
    Build an OrthoASession(test_mode=True). Pass fail_connect / fail_downloads to
    simulate error paths.

    Usage:
        session = make_session()
        session = make_session(fail_downloads={"users": OrthoAdl.OrthoADownloadError("boom")})
    """
    from orthoaget.session import OrthoASession

    def _make(fail_connect=None, fail_downloads=None):
        CONFIG.fail_connect = fail_connect
        CONFIG.fail_downloads = fail_downloads or {}
        return OrthoASession(test_mode=True)

    return _make
