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
        records  = session.get_proth_records()
        set_done = session.make_proth_set_done()
    set_done([records[0]["url"]])
"""

import json
import unicodedata
import requests
from datetime import datetime
from pathlib import Path

import yaml
from OrthoABase import DownloadDir
from OrthoABase.OrthoAData import OrthoADataParse, DEBUG_NO_DL_IN
from orthoaget import PROJECT_ROOT
from orthoaget.transform import build_context, get_open_days, transform_daily_events, transform_jt

URLS_FILE = f"{PROJECT_ROOT}/OrthoABase/urls.yaml"
USERS_DB_FILE = Path(PROJECT_ROOT) / "users_db.json"


def _normalize_str(s: str) -> str:
    """Lowercase, strip accents — used for case/accent-insensitive comparisons and sorting."""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").casefold()

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
            elif data_type == "json_paginated":
                data = self._parser.parseJsonPaginated(url, structure_name)
            elif data_type == "html":
                data = self._parser.parseHtml(url, structure_name)
            elif data_type == "html_paginated":
                data = self._parser.parseHtmlPaginated(url, structure_name)

            if not DEBUG_NO_DL_IN:
                DownloadDir.clearDownloadDir(self._download_dir)

            if data is not None:
                parsed_data[structure_name] = data

        return parsed_data
    
    def get_proth_records(self) -> list:
        """
        Fetch all prothesiste acts via JsonProth (paginated JSON).
        Each record contains all act fields plus:
          'url'         : full acte URL  (for set_actes_as_done)
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

    def set_proth_actes_as_done(self, acte_urls: list[str]) -> bool:
        """
        Mark acts as done while the session (driver) is still open.
        Grabs cookies from the live driver.
        """
        cookies = self._parser.orthoAdl.driver.get_cookies()
        for url in acte_urls:
            self._post_set_done_via_abspath(url, cookies)
        return True

    def make_proth_set_done(self):
        """
        Capture cookies now and return a callable(acte_urls) -> bool
        that works after the session is closed.

        Usage:
            with OrthoASession() as session:
                records  = session.get_proth_records()
                set_done = session.make_proth_set_done()
            set_done([records[0]["url"]])
        """
        cookies = self._parser.orthoAdl.driver.get_cookies()

        def set_done(acte_urls: list[str]) -> bool:
            for url in acte_urls:
                self._post_set_done_via_abspath(url, cookies)
            return True

        return set_done

    @staticmethod
    def _post_set_done_via_abspath(acte_url: str, cookies: list[dict]) -> bool:
        """GET the act page, parse the form, POST back with done=1."""
        from bs4 import BeautifulSoup

        req_session = requests.Session()
        for cookie in cookies:
            req_session.cookies.set(
                cookie["name"], cookie["value"],
                domain=cookie.get("domain"), path=cookie.get("path", "/"),
            )

        get_resp = req_session.get(acte_url, timeout=10, allow_redirects=True)
        if get_resp.status_code != 200:
            raise RuntimeError(f"GET {acte_url} failed: HTTP {get_resp.status_code}")
        if get_resp.url.rstrip("/") != acte_url.rstrip("/"):
            raise RuntimeError(f"Session expirée : redirigé vers {get_resp.url}")

        soup = BeautifulSoup(get_resp.text, "html.parser")
        forms = soup.find_all("form")
        form = next(
            (f for f in forms if str(f.get("method", "")).lower() == "post"),
            forms[0] if forms else None,
        )
        if not form:
            raise RuntimeError(f"No form found at {acte_url}")

        form_data = {}

        for tag in form.find_all("input"):
            name = tag.get("name")
            if not name:
                continue
            input_type = str(tag.get("type", "text")).lower()
            if input_type in ("checkbox", "radio"):
                if tag.has_attr("checked"):
                    form_data[name] = tag.get("value", "on")
            elif input_type != "submit":
                form_data[name] = tag.get("value", "")

        for tag in form.find_all("select"):
            name = tag.get("name")
            if not name:
                continue
            selected = tag.find("option", selected=True)
            if selected:
                form_data[name] = selected.get("value", "")
            else:
                first = tag.find("option")
                form_data[name] = first.get("value", "") if first else ""

        for tag in form.find_all("textarea"):
            name = tag.get("name")
            if name:
                form_data[name] = tag.get_text()

        form_data["done"] = "1"

        cookie_header = "; ".join(
            f"{c['name']}={c['value']}" for c in cookies
        ).replace('"', '\\"')
        data_args = " ".join(f'-F "{k}={v}"' for k, v in form_data.items())
        print(f'curl -X POST "{acte_url}" -H "Cookie: {cookie_header}" {data_args} -L')

        post_resp = req_session.post(
            acte_url,
            data=form_data,
            allow_redirects=True,
            timeout=10,
        )
        if post_resp.status_code in (200, 302):
            return True
        raise RuntimeError(f"POST to {acte_url} failed: HTTP {post_resp.status_code}")

    def get_users_records(self):
        data = self.extract(["users"])
        return data['users']
    
    def get_stats_records(self) -> dict:
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
        data = self.extract(["users", "rdvs_all", "MetatypesFauteuils"])

        users     = data.get("users", [])
        rdvs      = data.get("rdvs_all", [])
        metatypes = data.get("MetatypesFauteuils", {}).get("metatypes", {})

        # Plage planning value (e.g. "P55") -> {temps_praticien, temps_total}
        plage_lookup = {
            v["value"]: {"temps_praticien": v.get("dr", 0), "temps_total": v.get("duree", 0)}
            for v in metatypes.values()
        }

        # Patient name (title-cased) -> id
        name_to_id = {u["name"].strip().title(): u["id"] for u in users}

        # Init result with user params — no id, no name
        result = {
            str(u["id"]): {k: v for k, v in u.items() if k not in ("id", "name")} | {"rdvs": []}
            for u in users
        }

        for rdv in rdvs:
            patient_name = rdv.get("Patient", "").strip().title()
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

            result[str(patient_id)]["rdvs"].append({"date": date, "plage": plage, **times})

        return result

    def get_calendar_records(self) -> dict:
        """
        Fetch the full planning configuration from OrthoAdvance.
        Returns a dict with keys: 'alldaysyear', 'jt', 'metatypes', 'rdvs_history'.
        Requires entries in urls.yaml for: jt, metatypes, alldaysyear, rdvs_history.
        """
        base = self.extract(["users", "MetatypesFauteuils", "jt", "alldaysyear", "rdvs_history"], params = {"year": datetime.now().strftime("%Y")})
        days_next_year = self.extract(["alldaysyear"], params = {"year": str(int(datetime.now().strftime("%Y"))+1)})
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

    def get_echeances_records(self, dayin: str, dayout: str) -> list:
        """
        Get payment schedule records for the given date range.

        Parameters
        ----------
        dayin  : start date, "YYYY-MM-DD"
        dayout : end date,   "YYYY-MM-DD"
        """
        data = self.extract(["echeances"], params={"date_start": dayin, "date_end": dayout})
        return data["echeances"]

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

    def user_url(self, user_id) -> str:
        """Return the OrthoAdvance clinique URL for a given user ID."""
        return f"{self._parser.orthoAdl.OrthoAUrlBase}/ang/#!/users/{user_id}/clinique/compact/"

    def get_html_table_items(self, url_name: str) -> list[dict]:
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
        items = self.get_html_table_items(url_name)
        sorted_items = sorted(items, key=lambda x: _normalize_str(x["title"]))

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
        self.end()
