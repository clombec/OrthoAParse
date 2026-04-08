import datetime
from . import OrthoAdl
import logging
import os
import csv
import pandas as pd
from . import DownloadDir
import json
import yaml
from bs4 import BeautifulSoup
from datetime import datetime
import re
from orthoaget import PROJECT_ROOT

DEBUG_NO_DL_IN = False

class OrthoADataParse():
    def __init__(self, download_dir):
        if not os.path.exists(download_dir) or not os.listdir(download_dir):
            self.DEBUG_NO_DL = False
        else:
            self.DEBUG_NO_DL = DEBUG_NO_DL_IN
        if self.DEBUG_NO_DL:
            self.orthoAdl = OrthoAdl.OrthoAdl(download_dir, no_dl=True)
        else:
            self.orthoAdl = OrthoAdl.OrthoAdl(download_dir)  # raises OrthoAConnectionError if login fails
        self.cleanUpSwitch = {
            "rdvs_history": self.cleanUpCsv,
            "jt": self.cleanUpJourneesType,
            "metatypes": self.cleanUpMetatypes,
            "users": self.cleanUpUsers,
            "alldays2026": self.cleanUpJt2026,
            "prothesiste": self.cleanUpCsv,
            "recette": self.cleanUpCsv,
            "journees_type": self.cleanUpJourneesType,
            "stat_periodes": self.cleanUpCsv,
        }
        self.dataKeys = {}

    def end(self):
        self.orthoAdl.end()

    def parseCsv(self, csv_url, structure_name):
        rows = None
        if not self.DEBUG_NO_DL:
            csv_file = self.orthoAdl.downloadCsv(csv_url)  # raises OrthoADownloadError on failure
        else:
            csv_file = os.path.join(self.orthoAdl.download_dir, "export.csv")
        logging.info(f"Looking for CSV file at {csv_file}")
        if os.path.exists(csv_file):
            # Use pandas read_csv with python engine for more lenient parsing in the face of mixed separators.
            df = pd.read_csv(
                csv_file,
                encoding="utf-8",
                sep=None,
                quotechar='"',
                quoting=csv.QUOTE_ALL,   # or QUOTE_MINIMAL depending on your file
                engine="python"          # more tolerant than C engine
            ).fillna("")

            rows = self.cleanUp(df, structure_name)

        return rows

    def parseJson(self, json_url, structure_name):
        rows = None
        if not self.DEBUG_NO_DL:
            self.orthoAdl.downloadPageText(json_url)  # raises OrthoADownloadError on failure
        json_file = os.path.join(self.orthoAdl.download_dir, "page_content.txt")
        if os.path.exists(json_file):
            with open(json_file, "r", encoding="utf-8") as f:
                data = f.read()
                json_data = json.loads(data)
                with open(os.path.join(self.orthoAdl.download_dir, "data.json"), "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2)

            rows = self.cleanUp(json_data, structure_name)

        return rows

    def parseHtml(self, html_url, structure_name):
        rows = None
        htmlpage = "page_content.html"
        if not self.DEBUG_NO_DL:
            self.orthoAdl.downloadPageHtml(html_url, htmlpage)  # raises OrthoADownloadError on failure
        html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                html_data = f.read()
                soup = BeautifulSoup(html_data, "html.parser")

            rows = self.cleanUp(soup, structure_name)

        return rows

    def parseMulti(self, index_url, structure_name):
        """
        Fetches all day types from OrthoAdvance:
        1. Downloads the index HTML page listing all day types
        2. Extracts day type IDs from /planning/jt/journees/<n> links
        3. For each ID, calls /planning/jt/journees/<n>/;view?json=1
        4. Parses and aggregates results into a dict keyed by day type ID
        """
        outdata = {}
        htmlpage = "page_content.html"

        if not self.DEBUG_NO_DL:
            self.orthoAdl.downloadPageHtml(index_url, htmlpage)  # raises OrthoADownloadError on failure

        html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
        if not os.path.exists(html_file):
            logging.error(f"[parseMulti] Index file not found: {html_file}")
            return outdata

        with open(html_file, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Extract unique day type IDs and their labels from anchor links
        journee_ids = []  # list of (id, label) tuples
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'planning/preparation/jtypes/' in href:
                match = re.search(r'/jtypes/(\d+)', href)
                if match:
                    jid = int(match.group(1))
                    if jid not in [j[0] for j in journee_ids]:
                        nav_title = link.find('span', class_='nav-title')
                        label = nav_title.get_text(strip=True) if nav_title else None
                        journee_ids.append((jid, label))

        logging.info(f"[parseMulti] {len(journee_ids)} day types found: {[j[0] for j in journee_ids]}")

        # Fetch and parse each day type individually
        for jid, label in journee_ids:
            json_url = f"/planning/jt/journees/{jid}/;view?json=1"
            logging.info(f"[parseMulti] Parsing day type {jid} ({label})...")
            try:
                rows = self.parseJson(json_url, structure_name)
            except OrthoAdl.OrthoADownloadError as e:
                # Log and skip this day type — don't abort the whole multi fetch
                logging.warning(f"[parseMulti] Skipping day type {jid}: {e}")
                continue
            if rows is not None:
                outdata[jid] = {
                    "label": label,
                    "sequences": rows
                }

        logging.info(f"[parseMulti] Done — {len(outdata)} day types parsed")
        return outdata

    def cleanUpJourneesType(self, datain, structure_name):
        """
        Parses a journée type from /planning/jt/journees/<n>/;view?json=1
        Extracts sequences (metatype_id → {as1, dr, as2})
        enriched with value/color from enumerates.metatypes.list
        """
        sequences = datain.get("sequences", {})
        metatypes_list = datain.get("enumerates", {}).get("metatypes", {}).get("list", [])

        # Build a lookup dict of name/color by metatype_id
        meta_info = {}
        for meta in metatypes_list:
            meta_id = int(meta["name"].split("/")[-1])
            meta_info[meta_id] = {
                "value": meta.get("value"),
                "color": meta.get("color"),
            }

        # Build output list — one row per active metatype (at least one non-zero duration)
        out = []
        for key, roles in sequences.items():
            meta_id = int(key.split("/")[-1])
            # Skip metatypes with all-zero durations — not scheduled in this day type
            if not any(roles.values()):
                continue
            row = {
                "metatype_id": meta_id,
                "as1": roles.get("as1", 0),
                "dr": roles.get("dr", 0),
                "as2": roles.get("as2", 0),
            }
            row.update(meta_info.get(meta_id, {"value": None, "color": None}))
            out.append(row)

        return out


    def cleanUpCsv(self, dfin, structure_name):
        keys = self.dataKeys.get(structure_name)
        if keys is None:
            df_filtered = dfin  # no keys defined — keep all columns
        else:
            # Keep only columns defined in keys
            df_filtered = dfin.loc[:, dfin.columns.intersection(keys)]

        if isinstance(df_filtered, pd.Series):
            df_filtered = df_filtered.to_frame()

        data = df_filtered.to_dict(orient="records")

        if structure_name == "rdvs_history":
            for item in data:
                dt = datetime.strptime(
                    item.pop("Date et heure du RDV"),
                    "%d/%m/%Y %Hh%M"
                )
                item["Date et heure du RDV"] = dt.isoformat()

        if structure_name == "prothesiste":
            for item in data:
                dt = datetime.fromisoformat(item.pop("Date du rdv"))
                item["Date du rdv"] = dt.isoformat()
                pe_date_str = item.pop("PE", "")
                if pe_date_str == "":
                    item["PE"] = None
                else:
                    dt = datetime.fromisoformat(pe_date_str)
                    item["PE"] = dt.isoformat()
                dt = datetime.strptime(item.pop("Date d'envoi au labo"), "%d/%m/%Y").date()
                item["Date d'envoi au labo"] = dt.isoformat()
                dt = datetime.strptime(item.pop("Date de réception"), "%d/%m/%Y").date()
                item["Date de réception"] = dt.isoformat()
        return data

    def cleanUpCalendarEvents(self, datain, structure_name):
        events = datain["events"]
        keys = self.dataKeys.get(structure_name)

        #To avoid not subscriptable error if keys is not defined or not a list/tuple
        if keys is None or not isinstance(keys, (list, tuple)):
            logging.error(f"Error: dataKeys for {structure_name} is not subscriptable")
            return []

        # Filter data from input based on keys defined in url.yaml for this structure
        # Keep only the whitelisted columns for calendaring events.
        filtered_data = [
            {k: d[k] for k in keys if k in d}
            for d in events
        ]

        return filtered_data

    """
    This clean up is specific to the metatypes structure, a JSON file with a specific format.
    The data cannot be retrieved with a single list of keys as they're nested, hence the parsing must be hardcoded
    """
    def cleanUpMetatypes(self, datain, structure_name):
        journees = datain

        sequences = journees["sequences"]
        metatypes_list = journees["enumerates"]["metatypes"]["list"]

        out_struct = {}

        for key, roles in sequences.items():
            metatype_id = int(key.split("/")[-1])
            out_struct[metatype_id] = roles.copy()

        for meta in metatypes_list:
            metatype_id = int(meta["name"].split("/")[-1])

            out_struct.setdefault(metatype_id, {})
            out_struct[metatype_id].update({
                "value": meta.get("value"),
                "duree": meta.get("duree"),
                "color": meta.get("color"),
            })

        return out_struct

    """
    Input data is a list of dicts, containing each : Nom, which is the user ID, Nom.1 = real name and Prénome.
    This clean up returns a list of dicts with only the user ID and the full name : "Prénom Nom.1"
    """
    def cleanUpUsers(self, dfin, structure_name):
        out_struct = []
        # Get the keys for this structure from the dataKeys dictionary, listed in url.yaml.
        keys = self.dataKeys.get(structure_name)

        #To avoid not subscriptable error if keys is not defined or not a list/tuple
        if keys is None or not isinstance(keys, (list, tuple)):
            logging.error(f"Error: dataKeys for {structure_name} is not subscriptable")
            return out_struct

        # Filter the DataFrame to keep only the columns specified in keys for this structure. This assumes that the keys are the column names in the DataFrame.
        df_filtered = dfin.loc[:, keys]

        # If the result is a Series (which happens if there's only one column), convert it to a DataFrame to ensure consistent processing. This is necessary because the next steps expect a DataFrame structure, even if it's just one column.
        if isinstance(df_filtered, pd.Series):
            # Convert the Series to a DataFrame, which will have one column with the name of the original Series.
            df_filtered = df_filtered.to_frame()

        # Convert the filtered DataFrame to a list of dictionaries, where each dictionary represents a row with column names as keys. This makes it easier to iterate over the data and extract the relevant information for each user.
        df_records = df_filtered.to_dict(orient="records")

        patientId = keys[0]  # Assuming the first key is the user ID
        lastName = keys[1]   # Assuming the second key is the last name
        firstName = keys[2]  # Assuming the third key is the first name

        for user in df_records:
            # Create out structure with only the user ID and the full name "Prénom Nom"
            out_struct.append({
                "id": user.get(patientId),  # Assuming the first key is the user ID
                "name": f"{user.get(firstName)} {user.get(lastName)}", # Assuming the second key is the last name and the third key is the first name
                "url": f"{self.orthoAdl.OrthoAUrlBase}/ang/#!/users/<ID>/clinique/compact/"  # Static URL for the user clinique view. Final URL is built when displayed with Django users DB in OrthoAPnD
            })
        return out_struct

    """
    This clean up is specific to the JT2026 structure, which is an HTML table with a specific format. It extracts the relevant columns based on the keys defined in url.yaml for this structure, and returns a list of lists containing the cleaned data.
    It is base don a beautiful soup object, which is passed to the cleanUp function
    """
    def cleanUpJt2026(self, soupin, structure_name):
        out_struct = []

        # Get the html table with id "browse-list"
        table = soupin.find('table', id='browse-list')

        # get the headers of the table
        headers = [th.get_text(strip=True) for th in table.thead.find_all('th')]

        # extract the keys for this structure from the dataKeys dictionary, listed in url.yaml. These keys correspond to the column names in the HTML table that we want to keep.
        keys = self.dataKeys.get(structure_name)

        #To avoid not subscriptable error if keys is not defined or not a list/tuple
        if keys is None or not isinstance(keys, (list, tuple)):
            logging.error(f"Error: dataKeys for {structure_name} is not subscriptable")
            return out_struct

        # get the indexes of the columns to keep based on the headers and the keys
        indexes = [headers.index(col) for col in keys]

        # Iterate over the rows of the table body and extract the text of the cells corresponding to the indexes of the columns to keep, then append the cleaned data to the output structure as a list of lists.
        for row in table.tbody.find_all('tr'):
            cells = row.find_all('td')
            line = [cells[i].get_text(strip=True) for i in indexes]
            out_struct.append(line)

        return out_struct

    """
    This function is a generic cleanup function that calls the appropriate specific cleanup function based on the structure name.
    It uses a dictionary of cleanup functions (cleanUpSwitch) to map structure names to their corresponding cleanup functions.
    If no specific cleanup function is defined for a structure, it returns the input data unchanged.
    """
    def cleanUp(self, datain, structure_name):
        return self.cleanUpSwitch.get(structure_name, lambda x, y: x)(datain, structure_name)


URLS_FILE = f"{PROJECT_ROOT}/OrthoABase/urls.yaml"

"""
Download and parse a subset of OrthoAdvance data.

Parameters
----------
entries   : list of entry names to fetch (e.g. ["prothesiste", "users"]).
            Must match top-level entries in urls.yaml.
urls_file : path to the global urls.yaml (defaults to OrthoABase/urls.yaml).

Raises OrthoAdl.OrthoAConnectionError if login fails.
Raises OrthoAdl.OrthoADownloadError if a download fails.
Raises KeyError if a requested entry is not found in urls.yaml.
"""
def extract(entries: list, urls_file: str = URLS_FILE):
    download_dir = DownloadDir.setupDownloadDir("downloads")
    if not DEBUG_NO_DL_IN:
        DownloadDir.clearDownloadDir(download_dir)

    with open(urls_file, "r", encoding="utf-8") as f:
        all_urls = yaml.safe_load(f)

    if entries is None:
        entries = list(all_urls.keys())

    missing = [e for e in entries if e not in all_urls]
    if missing:
        raise KeyError(f"Entries not found in {urls_file}: {missing}")

    # OrthoADataParse.__init__ calls OrthoAdl.connect() — raises OrthoAConnectionError if it fails
    orthoAdp = OrthoADataParse(download_dir)

    parsed_data = {}
    for structure_name in entries:
        structure_config = all_urls[structure_name]
        url = structure_config.get("url")
        data_type = structure_config.get("type")
        orthoAdp.dataKeys[structure_name] = structure_config.get("keys", None)

        data = None
        if data_type == "csv":
            data = orthoAdp.parseCsv(url, structure_name)
        elif data_type == "json":
            data = orthoAdp.parseJson(url, structure_name)
        elif data_type == "html":
            data = orthoAdp.parseHtml(url, structure_name)
        elif data_type == "multi":
            data = orthoAdp.parseMulti(url, structure_name)

        if not DEBUG_NO_DL_IN:
            DownloadDir.clearDownloadDir(download_dir)

        if data is not None:
            parsed_data[structure_name] = data

    orthoAdp.end()

    return parsed_data

def main():
    OrthoAdata = extract(["rdvs_history", "users"])
    with open("data.json", "w") as f:
        json.dump(OrthoAdata, f, indent=2)

    for rdv in OrthoAdata["rdvs_history"]:
        patient_name = rdv.get("Patient")
        user = next((u for u in OrthoAdata["users"] if u["name"].lower() == patient_name.lower()), None)
        if user:
            patient_id = user["id"]
            logging.info(f"Rendez-vous for patient {patient_name} (ID: {patient_id})")
        else:
            logging.warning(f"Rendez-vous for patient {patient_name} (ID: not found)")

if __name__ == "__main__":
    main()