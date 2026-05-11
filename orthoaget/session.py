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

import json
from datetime import datetime
from pathlib import Path

import yaml
from OrthoABase import DownloadDir
from OrthoABase.OrthoAData import OrthoADataParse, DEBUG_NO_DL_IN
from orthoaget import PROJECT_ROOT
from orthoaget.transform import build_context, get_open_days, transform_daily_events, transform_jt

URLS_FILE = f"{PROJECT_ROOT}/OrthoABase/urls.yaml"
USERS_DB_FILE = Path(PROJECT_ROOT) / "users_db.json"

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

        # Give the parser access to the full urls.yaml config
        self._parser.urlsConfig = self._all_urls

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

            data = None
            if data_type == "csv":
                data = self._parser.parseCsv(url, structure_name)
            elif data_type == "json":
                data = self._parser.parseJson(url, structure_name)
            elif data_type == "html":
                data = self._parser.parseHtml(url, structure_name)

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

    def get_calendar_records(self) -> dict:
        """
        Fetch the full planning configuration from OrthoAdvance.
        Returns a dict with keys: 'alldaysyear', 'jt', 'metatypes', 'rdvs_history'.
        Requires entries in urls.yaml for: jt, metatypes, alldaysyear, rdvs_history.
        """
        base = self.extract(["users", "MetatypesFauteuils", "jt", "alldaysyear", "rdvs_history"], params = {"year": datetime.now().strftime("%y")})
        days_next_year = self.extract(["alldaysyear"], params = {"year": str(int(datetime.now().strftime("%y"))+1)})
        base["alldaysyear"].extend(days_next_year["alldaysyear"])
        ctx = build_context(base)

        jt_tables = transform_jt(base["jt"], ctx)
        open_days = get_open_days(base["alldaysyear"])

        all_events = []
        for day in open_days:
            daily = self.extract(["daily_calendar"], params={"day": day["date"]})
            events = transform_daily_events(daily["daily_calendar"], base["rdvs_history"], ctx)
            all_events.extend(events)

        data = {
            "jt": jt_tables,
            "events": all_events,
            "alldaysyear": open_days,
        }
        return data

    def _load_users_db(self) -> dict:
        """Load the local users DB {str(id): {name, user_color, ...}} from disk, or return empty dict."""
        if USERS_DB_FILE.exists():
            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_users_db(self, db: dict) -> None:
        with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

    def _build_users_db(self) -> dict:
        """Fetch users from OrthoAdvance (already enriched with user_params by cleanUpUsers) and save to DB."""
        users = self.extract(["users"])["users"]
        db = {str(u["id"]): {k: v for k, v in u.items() if k != "id"} for u in users}
        self._save_users_db(db)
        return db

    def get_user_by_id(self, user_id: int) -> dict | None:
        """Return the full user record {name, user_color, ...} for a given id. Fetches from DB first."""
        db = self._load_users_db()
        key = str(user_id)
        if key not in db:
            db = self._build_users_db()
        return db.get(key)

    def get_name_by_id(self, user_id: int) -> str | None:
        """Return the name for a given user id."""
        user = self.get_user_by_id(user_id)
        return user.get("name") if user else None

    def get_income_records(self, dayin = datetime.now().strftime("%Y-%m-%d"), dayout = datetime.now().strftime("%Y-%m-%d")) -> list:
        """
        Get income data for a specific date range. Default : today only
        """
        data = self.extract(["recette_jour"], params={"dayin": dayin, "dayout": dayout})
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
