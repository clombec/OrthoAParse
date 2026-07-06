"""
session.py

OrthoASession — single-connection facade over OrthoADataParse.

One Chrome session is opened on __init__() and reused across all extract() calls.
Call end() when done to close the browser.

Usage:
    session = OrthoASession()
    proth = session.get_proth_records()
    users = session.extract(["users"])
    url   = session.user_url(42)
    session.end()

Or as a context manager:
    with OrthoASession() as session:
        records = session.get_proth_records()
        form_data, form_display, is_expired = session.fetch_act(records[0]["url"])
        if not is_expired:
            session.confirm_act_done(records[0]["url"], form_data)

Testing, without a real Selenium/OrthoAdvance connection — everything above OrthoAdl
(parsing, cleanUp, session logic) still runs for real, only the browser layer is
simulated (see tests/fakes/fake_orthoadl.py and tests/fakes/test_config.py for the
fixed fixtures/users_db paths and per-test error injection):
    with OrthoASession(test_mode=True) as session:
        users = session.get_users_list()
"""

import json
import logging
import os
import requests
from datetime import datetime
from pathlib import Path

import yaml
from OrthoABase import DownloadDir
from OrthoABase.OrthoAData import OrthoADataParse
from orthoaget import PROJECT_ROOT
from orthoaget.transform import build_context, build_name_map, get_open_days, transform_daily_events, transform_jt, normalize_name

URLS_FILE = f"{PROJECT_ROOT}/OrthoABase/urls.yaml"
USERS_DB_FILE = Path(PROJECT_ROOT) / "users_db.json"



class OrthoASession:
    def __init__(self, urls_file: str = URLS_FILE, get_all_user_data: bool | None = None,
                 test_mode: bool = False):
        """
        test_mode : if True, everything below OrthoASession runs against FakeOrthoAdl
                    instead of a real Selenium/OrthoAdvance connection — parsing, cleanUp
                    and session logic still run for real. OrthoASession itself never
                    imports OrthoAdl or FakeOrthoAdl: it only forwards this bool to
                    OrthoADataParse, which is the one place that decides between the real
                    and fake implementations. This is the only test-related parameter on
                    OrthoASession. Per-test error injection (connection/download failures)
                    goes through the shared CONFIG object in tests/fakes/test_config.py.
        """
        self._urls_file = urls_file
        with open(urls_file, "r", encoding="utf-8") as f:
            self._all_urls = yaml.safe_load(f)

        self._users_db_file = USERS_DB_FILE

        self._download_dir = DownloadDir.setupDownloadDir("downloads")
        DownloadDir.clearDownloadDir(self._download_dir)

        # Single connect — Chrome starts here (or FakeOrthoAdl, in test_mode)
        self._parser = OrthoADataParse(self._download_dir, test_mode=test_mode)
        try:
            # Give the parser access to the full urls.yaml config
            self._parser.urlsConfig = self._all_urls

            if get_all_user_data is None:
                get_all_user_data = os.environ.get("GET_ALL_USER_DATA", "").lower() in ("1", "true")
            self._get_all_user_data = get_all_user_data

            # In-memory users cache — loaded from disk, written back on every change
            self._users_cache: dict[str, dict] = {}
            self._load_users_db()
        except Exception:
            self._parser.end()
            raise

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
            elif data_type == "json_paginated":
                data = self._parser.parseJsonPaginated(url, structure_name)
            elif data_type == "html":
                data = self._parser.parseHtml(url, structure_name)
            elif data_type == "html_paginated":
                data = self._parser.parseHtmlPaginated(url, structure_name)
            elif data_type == "html_form":
                data = self._parser.parseHtmlForm(url)

            DownloadDir.clearDownloadDir(self._download_dir)

            if data is not None:
                parsed_data[structure_name] = data

        return parsed_data
    
    def get_proth_records(self) -> list:
        """
        Fetch all prothesiste acts via JsonProth (paginated JSON).
        Each record contains all act fields plus:
          'url'         : full acte URL  (for fetch_act / confirm_act_done)
          'patient_url' : full patient clinique URL
        """
        data = self.extract(["JsonProth"])
        records = data.get("JsonProth", [])
        base_url = self._parser.orthoAdl.OrthoAUrlBase
        for rec in records:
            rec["url"] = f"{base_url}{rec.get('abspath', '')}"
            if rec.get("patient_url"):
                rec["patient_url"] = f"{base_url}{rec['patient_url']}"
        return records

    def fetch_act(self, url: str) -> tuple[dict | None, dict | None, bool]:
        """
        GET a single act page and parse its form fields.
        Returns (form_data, form_display, is_expired).
        - form_data:    raw values for POST (pass to confirm_act_done)
        - form_display: same but select fields show their text label instead of the path value
        - is_expired:   True if the session has expired (redirect detected)
        """
        result = self.extract(["acte_form"], params={"url": url}).get("acte_form")
        if result is None:
            return None, None, True
        return result["form_data"], result["form_display"], False

    def confirm_act_done(self, url: str, form_data: dict) -> bool:
        """Mark a single act as done using form_data returned by fetch_act."""
        return self._parser.postActDone(url, form_data)

    def get_users_records(self) -> list[dict]:
        return self.get_users_list()
    
    def get_user_rdv_records(self) -> dict:
        """
        Build per-patient stats from rdvs_all and users.

        Returns
        -------
        {str(patient_id): {
            "rdvs": [{"date": "YYYY-MM-DD", "temps_praticien": int, "temps_total": int}, ...],
            <user_params except name>   # user_statistics_group, archive_delay, ...
        }}
        Patients are identified by ID only — no name in output.
        """
        users = self.get_users_list()
        data  = self.extract(["rdvs_all", "MetatypesFauteuils"])

        rdvs      = data.get("rdvs_all", [])
        metatypes = data.get("MetatypesFauteuils", {}).get("metatypes", {})

        # Plage planning value (e.g. "P55") -> {temps_praticien, temps_total}
        plage_lookup = {
            v["value"]: {"temps_praticien": v.get("dr", 0), "temps_total": v.get("duree", 0)}
            for v in metatypes.values()
        }

        name_to_id, _ = build_name_map(users)

        # Init result with user params — no id, no name fields
        result = {
            str(u["id"]): {k: v for k, v in u.items() if k not in ("id", "last_name", "first_name")} | {"rdvs": []}
            for u in users
        }

        for rdv in rdvs:
            patient_name = normalize_name(rdv.get("Patient", "").strip())
            patient_id = name_to_id.get(patient_name)
            if patient_id is None:
                continue

            dt_str = rdv.get("Date et heure du RDV", "")
            try:
                date = datetime.strptime(dt_str, "%d/%m/%Y %Hh%M").date().isoformat()
            except ValueError:
                date = dt_str[:10]

            plage = rdv.get("Plage planning", "")
            times = plage_lookup.get(plage, {"temps_praticien": None, "temps_total": None})
            acte_type = rdv.get("Type d'acte", "")

            result[str(patient_id)]["rdvs"].append({"date": date, "plage": plage, "acte_type": acte_type, **times})

        return result

    def get_calendar_records(self) -> dict:
        """
        Fetch the full planning configuration from OrthoAdvance.
        Returns a dict with keys: 'alldaysyear', 'jt', 'metatypes', 'rdvs_history'.
        Requires entries in urls.yaml for: jt, metatypes, alldaysyear, rdvs_history.
        """
        base = self.extract(["MetatypesFauteuils", "jt", "alldaysyear", "rdvs_history"], params={"year": datetime.now().strftime("%Y")})
        days_next_year = self.extract(["alldaysyear"], params={"year": str(int(datetime.now().strftime("%Y")) + 1)})
        base["alldaysyear"].extend(days_next_year["alldaysyear"])
        base["users"] = self.get_users_list()
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
            "metatype_map": ctx["metatype_map"],
        }
        return data

    # ------------------------------------------------------------------
    # Users cache — in-memory dict, persisted to users_db.json
    # ------------------------------------------------------------------

    def _load_users_db(self) -> None:
        """Load users_db.json into self._users_cache. Called once at __init__."""
        if self._users_db_file.exists():
            with open(self._users_db_file, "r", encoding="utf-8") as f:
                self._users_cache = json.load(f)

    def _save_users_db(self) -> None:
        """Persist self._users_cache to users_db.json."""
        with open(self._users_db_file, "w", encoding="utf-8") as f:
            json.dump(self._users_cache, f, ensure_ascii=False, indent=2)

    def _sync_user_list(self) -> None:
        """
        Re-fetch the basic user list and add any new or renamed users to the cache.
        Saves only if something changed.
        """
        users = self.extract(["users"])["users"]
        changed = False
        for u in users:
            uid = str(u["id"])
            entry = self._users_cache.get(uid)
            if entry is None:
                self._users_cache[uid] = {
                    "last_name": u["last_name"],
                    "first_name": u["first_name"],
                    "params_fetched": not self._get_all_user_data,
                }
                changed = True
            elif entry.get("last_name") != u["last_name"] or entry.get("first_name") != u["first_name"]:
                entry["last_name"] = u["last_name"]
                entry["first_name"] = u["first_name"]
                changed = True
        if changed:
            self._save_users_db()

    def _fetch_user_params(self, user_id: int) -> None:
        """
        Fetch extended params (user_color, archive_delay, …) for one user,
        update the cache, and save immediately so progress survives a crash.
        """
        uid = str(user_id)
        if uid not in self._users_cache:
            return
        try:
            data = self.extract(["user_params"], params={"user_id": user_id})
            params = data.get("user_params") or {}
        except Exception as e:
            logging.warning(f"[users_db] Failed to fetch params for user {user_id}: {e}")
            return
        self._users_cache[uid].update(params)
        self._users_cache[uid]["params_fetched"] = True
        self._save_users_db()

    def refresh_users_db(self) -> None:
        """
        Full rebuild: fetch all users then, if self._get_all_user_data is True, fetch
        extended params per user with an incremental save after each one.
        """
        users = self.extract(["users"])["users"]
        self._users_cache = {
            str(u["id"]): {
                "last_name": u["last_name"],
                "first_name": u["first_name"],
                "params_fetched": not self._get_all_user_data,
            }
            for u in users
        }
        if not self._get_all_user_data:
            self._save_users_db()
            return
        for uid in list(self._users_cache):
            self._fetch_user_params(int(uid))  # saves after each user

    def get_users_list(self) -> list[dict]:
        """
        Return all users as [{id, last_name, first_name, …}] from the local cache.
        Syncs from OrthoAdvance if the cache is empty.
        The internal 'params_fetched' flag is stripped from the output.
        """
        if not self._users_cache:
            self._sync_user_list()
        return [
            {"id": int(uid), **{k: v for k, v in u.items() if k != "params_fetched"}}
            for uid, u in self._users_cache.items()
        ]

    def get_user_by_id(self, user_id: int) -> dict | None:
        """
        Return the full record for a given user ID, syncing from OrthoAdvance if not found.
        If self._get_all_user_data is True and extended params are missing, fetches them on demand.
        Returns None if the user does not exist.
        """
        uid = str(user_id)
        if uid not in self._users_cache:
            self._sync_user_list()
        if uid not in self._users_cache:
            return None
        if self._get_all_user_data and not self._users_cache[uid].get("params_fetched", False):
            self._fetch_user_params(user_id)
        user = self._users_cache[uid]
        return {k: v for k, v in user.items() if k != "params_fetched"}

    def get_name_by_id(self, user_id: int) -> str | None:
        """Return 'Prénom Nom' for a given user id."""
        user = self.get_user_by_id(user_id)
        if user is None:
            return None
        return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or None

    def _name_to_id_map(self) -> dict[str, int]:
        """Build a name→id map (both orderings, accent-stripped) from the local users cache."""
        name_to_id, _ = build_name_map(self.get_users_list())
        return name_to_id

    @staticmethod
    def _resolve_name(name: str, name_to_id: dict[str, int]) -> int | None:
        """Look up a patient name (accent-insensitive). Both orderings are pre-indexed in name_to_id."""
        return name_to_id.get(normalize_name(name.strip()))

    def get_echeances_records(self, dayin: str, dayout: str) -> list:
        """
        Get payment schedule records for the given date range.
        Patient names are replaced by their numeric ID.

        Parameters
        ----------
        dayin  : start date, "YYYY-MM-DD"
        dayout : end date,   "YYYY-MM-DD"

        Raises
        ------
        KeyError if a patient name cannot be resolved to an ID even after syncing.
        """
        data = self.extract(["echeances"], params={"dayin": dayin, "dayout": dayout})
        records = data["echeances"]
        name_to_id = self._name_to_id_map()
        missing = {
            rec["ID Patient"]
            for rec in records
            if rec.get("ID Patient") and self._resolve_name(rec["ID Patient"], name_to_id) is None
        }
        if missing:
            self._sync_user_list()
            name_to_id = self._name_to_id_map()
            still_missing = {n for n in missing if self._resolve_name(n, name_to_id) is None}
            if still_missing:
                raise KeyError(f"Unknown patients (not in users DB): {sorted(still_missing)}")
        for rec in records:
            name = rec.get("ID Patient")
            if name:
                rec["ID Patient"] = self._resolve_name(name, name_to_id)
        return records

    def get_income_records(self, dayin = None, dayout = None) -> list:
        """
        Get income data for a specific date range. Default : today only
        """
        if dayin is None:
            dayin = datetime.now().strftime("%Y-%m-%d")
        if dayout is None:
            dayout = datetime.now().strftime("%Y-%m-%d")
        data = self.extract(["recette_jour"], params={"dayin": dayin, "dayout": dayout})
        return data["recette_jour"]

    def get_anonymized_user_params(self) -> dict[str, dict]:
        """
        Return all users from the local cache, anonymised (no last_name / first_name).
        Keys are str(user_id); values are the stored params minus identity fields.
        Syncs from OrthoAdvance if the cache is empty.
        """
        if not self._users_cache:
            self._sync_user_list()
        excluded = {"last_name", "first_name", "params_fetched"}
        return {
            uid: {k: v for k, v in u.items() if k not in excluded}
            for uid, u in self._users_cache.items()
        }

    def get_anonymized_data(self) -> dict:
        """
        Aggregate all anonymised stats into a single dict:
          - 'rdvs'     : get_user_rdv_records()
          - 'calendar' : get_calendar_records()
          - 'echeances': get_echeances_records("2022-01-01", "2027-12-31")
          - 'stats'    : extract(["stat_periodes"])["stat_periodes"]
        No patient or user names appear in the output.
        """
        return {
            "users_rdvs":      self.get_user_rdv_records(),
            "calendar":  self.get_calendar_records(),
            "echeances": self.get_echeances_records(dayin="2022-01-01", dayout="2027-12-31"),
            "stats":     self.extract(["stat_periodes"]).get("stat_periodes"),
        }

    def user_url(self, user_id) -> str:
        """Return the OrthoAdvance clinique URL for a given user ID."""
        return f"{self._parser.orthoAdl.OrthoAUrlBase}/ang/#!/users/{user_id}/clinique/compact/"

    def _get_html_table_items(self, url_name: str) -> list[dict]:
        """
        Return [{path, title}] for all rows of a paginated HTML browse-list table.
        url_name must be a key in urls.yaml with type "html_paginated".
        """
        return self.extract([url_name])[url_name]

    def sort_html_table_items(self, url_name: str) -> list[dict]:
        """
        Sort all items of a paginated HTML table alphabetically by title
        (case/accent-insensitive). Reorders by POSTing order_top in reverse
        alphabetical order so the first item ends at position 1.

        Returns the sorted list [{path, title}].
        """
        items = self._get_html_table_items(url_name)
        sorted_items = sorted(items, key=lambda x: normalize_name(x["title"]))

        base_url_path = self._all_urls[url_name]["url"].split("?")[0]
        cookies = self._parser.orthoAdl.driver.get_cookies()
        base_url = self._parser.orthoAdl.OrthoAUrlBase
        for item in reversed(sorted_items):
            self._post_table_reorder(item["path"], "order_top", cookies, base_url, base_url_path)

        return sorted_items

    @staticmethod
    def _post_table_reorder(
        path: str, action: str, cookies: list[dict], base_url: str, url_path: str
    ) -> None:
        """POST <url_path> with ids=<path>&action=<action>."""
        req_session = requests.Session()
        for cookie in cookies:
            req_session.cookies.set(
                cookie["name"], cookie["value"],
                domain=cookie.get("domain"), path=cookie.get("path", "/"),
            )
        response = req_session.post(
            f"{base_url}/{url_path}",
            data={"ids": path, "action": action},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True,
            timeout=10,
        )
        if response.status_code not in (200, 302):
            raise RuntimeError(
                f"Table reorder failed for {path} (action={action}): HTTP {response.status_code}"
            )

    def end(self):
        """Close the browser session."""
        self._parser.end()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            self.end()
        except Exception:
            logging.exception("OrthoASession: error during cleanup")

