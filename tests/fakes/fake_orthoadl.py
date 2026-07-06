"""
fake_orthoadl.py

FakeOrthoAdl — drop-in replacement for OrthoABase.OrthoAdl.OrthoAdl used in tests.

Same constructor signature as the real OrthoAdl (__init__(self, download_dir)) so
OrthoADataParse(test_mode=True) can instantiate it exactly like the real class, with no
factory glue needed. Never touches a browser: downloads are served from
FIXTURES_ROOT/<structure name>/input.* files instead of OrthoAdvance.

fixtures_root and the urls.yaml config are fixed constants, not constructor parameters —
there is exactly one test fixtures tree. Per-test error injection (fail_connect /
fail_downloads) goes through the shared CONFIG object in test_config.py instead of
constructor arguments, so nothing needs to be threaded through OrthoASession/OrthoADataParse.
"""

import os
import shutil
from pathlib import Path

import yaml

from orthoaget import PROJECT_ROOT
from tests.fakes.test_config import CONFIG

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"

_URLS_FILE = Path(PROJECT_ROOT) / "OrthoABase" / "urls.yaml"


class _FakeDriver:
    """Stands in for the Selenium driver attribute a couple of session APIs read directly."""

    def get_cookies(self):
        return []


def _url_prefix(template_url: str) -> str:
    """Strip query string and stop at the first '{placeholder}' to get a stable matching prefix."""
    base = template_url.split("?")[0]
    if "{" in base:
        base = base.split("{")[0]
    return base.rstrip("/")


def _build_prefix_map() -> dict:
    """structure_name -> its urls.yaml url prefix (query string / placeholders stripped)."""
    with open(_URLS_FILE, "r", encoding="utf-8") as f:
        urls_config = yaml.safe_load(f)
    return {name: _url_prefix(cfg["url"]) for name, cfg in urls_config.items()}


class FakeOrthoAdl:
    def __init__(self, download_dir):
        self.download_dir = download_dir
        self.OrthoAUrlBase = "https://fake.orthoadvance.com"
        self.driver = _FakeDriver()
        self.calls: list[str] = []  # every pageUrl requested — useful for assertions

        self._prefix_map = _build_prefix_map()

        self.connect(download_dir)

    def connect(self, download_dir):
        if CONFIG.fail_connect is not None:
            raise CONFIG.fail_connect
        return  # simulate an immediate, successful login

    def _resolve(self, pageUrl: str) -> tuple[str, Path]:
        self.calls.append(pageUrl)
        base = pageUrl.split("?")[0].rstrip("/")
        matches = [
            (len(prefix), name)
            for name, prefix in self._prefix_map.items()
            if prefix and base.startswith(prefix)
        ]
        if not matches:
            raise AssertionError(
                f"FakeOrthoAdl: no structure in urls.yaml matches url {pageUrl!r}"
            )
        _, structure_name = max(matches)
        if structure_name in CONFIG.fail_downloads:
            raise CONFIG.fail_downloads[structure_name]
        return structure_name, FIXTURES_ROOT / structure_name

    @staticmethod
    def _input_file(folder: Path) -> Path:
        candidates = sorted(folder.glob("input.*"))
        if not candidates:
            raise FileNotFoundError(f"No input.* fixture found in {folder}")
        return candidates[0]

    def downloadCsv(self, pageUrl):
        _, folder = self._resolve(pageUrl)
        src = self._input_file(folder)
        dst = os.path.join(self.download_dir, os.path.basename(src))
        shutil.copy(src, dst)
        return dst

    def downloadPageHtml(self, pageUrl, filename="page_content.html"):
        _, folder = self._resolve(pageUrl)
        shutil.copy(self._input_file(folder), os.path.join(self.download_dir, filename))

    def downloadPageText(self, pageUrl, filename="page_content.txt", fullUrl=False):
        _, folder = self._resolve(pageUrl)
        shutil.copy(self._input_file(folder), os.path.join(self.download_dir, filename))

    def end(self):
        pass
