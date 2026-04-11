"""
session.py

OrthoASession — single-connection facade over OrthoADataParse.

One Chrome session is opened on __init__() and reused across all extract() calls.
Call end() when done to close the browser.

Usage:
    session = OrthoASession()
    proth = session.extract(["prothesiste"])
    users = session.extract(["users"])
    url   = session.user_url(42)
    session.end()

Or as a context manager:
    with OrthoASession() as session:
        data = session.extract(["prothesiste", "users"])
"""

from datetime import datetime

import yaml
from OrthoABase import DownloadDir
from OrthoABase.OrthoAData import OrthoADataParse, DEBUG_NO_DL_IN
from orthoaget import PROJECT_ROOT

URLS_FILE = f"{PROJECT_ROOT}/OrthoABase/urls.yaml"

class OrthoASession:
    def __init__(self, urls_file: str = URLS_FILE):
        self._urls_file = urls_file
        with open(urls_file, "r", encoding="utf-8") as f:
            self._all_urls = yaml.safe_load(f)

        self._download_dir = DownloadDir.setupDownloadDir("downloads")
        if not DEBUG_NO_DL_IN:
            DownloadDir.clearDownloadDir(self._download_dir)

        # Single connect — Chrome starts here
        self._parser = OrthoADataParse(self._download_dir)

    def extract(self, entries: list | None = None, params: dict | None = None) -> dict:
        """
        Download and parse the requested entries.
        Reuses the existing browser session — no reconnect.

        Parameters
        ----------
        entries : list of entry names matching top-level keys in urls.yaml.
                  If None or omitted, all entries from urls.yaml are fetched.
        params  : optional dict of placeholder substitutions applied to each URL
                  before fetching. Placeholders in urls.yaml use {key} syntax,
                  e.g. params={"month": "04"} replaces {month} in matching URLs.

        Raises KeyError if an entry is not found in urls.yaml.
        """
        if entries is None:
            entries = list(self._all_urls.keys())
        missing = [e for e in entries if e not in self._all_urls]
        if missing:
            raise KeyError(f"Entries not found in {self._urls_file}: {missing}")

        parsed_data = {}
        for structure_name in entries:
            structure_config = self._all_urls[structure_name]
            url = structure_config.get("url")
            if params:
                url = url.format_map(params)
            data_type = structure_config.get("type")
            self._parser.dataKeys[structure_name] = structure_config.get("keys", None)

            data = None
            if data_type == "csv":
                data = self._parser.parseCsv(url, structure_name)
            elif data_type == "json":
                data = self._parser.parseJson(url, structure_name)
            elif data_type == "html":
                data = self._parser.parseHtml(url, structure_name)
            elif data_type == "multi":
                data = self._parser.parseMulti(url, structure_name)

            if not DEBUG_NO_DL_IN:
                DownloadDir.clearDownloadDir(self._download_dir)

            if data is not None:
                parsed_data[structure_name] = data

        return parsed_data
    
    def get_proth_records(self):
        data = self.extract(["prothesiste"])
        return data['prothesiste']

    def get_users_records(self):
        data = self.extract(["users"])
        return data['users']

    def get_income_records(self, years = 0):
        """
        Get <years> last years of income data. Default is 0, which means only today. 1 is this year, 2 is this year and last year...
        """
        if years > 0:
            i = years
            full_data = []
            while i > 0:
                data = self.extract(["recettes_annuelles"], params={"year": str(datetime.now().year-(i-1))})
                full_data.extend(data['recettes_annuelles'])
                i -= 1
            return full_data
        else:
            data = self.extract(["recette_jour"])
            return data["recette_jour"]

    def user_url(self, user_id) -> str:
        """Return the OrthoAdvance clinique URL for a given user ID."""
        return f"{self._parser.orthoAdl.OrthoAUrlBase}/ang/#!/users/{user_id}/clinique/compact/"

    def end(self):
        """Close the browser session."""
        self._parser.end()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.end()
