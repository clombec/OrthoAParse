from cProfile import label
import datetime
from . import OrthoAdl
import logging
import os
import csv
import pandas as pd
import json
from bs4 import BeautifulSoup
from datetime import datetime
import re

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
            "MetatypesFauteuils": self.cleanUpMetatypesFauteuils,
            "users": self.cleanUpUsers,
            "alldays2026": self.cleanUpJt2026,
            "jt": self.cleanUpJt,
        }
        self.typeCleanUpSwitch = {
            "csv": self.cleanUpCsv,
            "json": self.cleanUpJson,
        }
        self.urlsConfig = {}

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


    def _cfg(self, structure_name):
        cfg = self.urlsConfig.get(structure_name, {})
        return cfg.get("keys"), cfg.get("subkeys")

    def cleanUpJson(self, datain, structure_name):
        keys, subkeys = self._cfg(structure_name)
        if not keys:
            return datain
        items = datain.get(keys[0], datain)
        if subkeys and isinstance(items, list):
            data = [{k: item.get(k) for k in subkeys} for item in items]
        else:             
            data = items
            
        return data

    """
        This clean up is specific to the JT structure :
        extracts data from json to get each Journée Type header
        Then launch downloand and parsing of the corresponding json for each journée type
    """
    def cleanUpJt(self, datain, structure_name):
        keys, subkeys = self._cfg(structure_name)
        if not keys:
            return datain
        items = datain.get(keys[0], datain)
        if subkeys and isinstance(items, list):
            data = [{k: item.get(k) for k in subkeys} for item in items]
        else:             
            return items

        jtdata = {}
        for item in data:
            jid = int(item.get("name", ""))
            label = item.get('title')
            jt_json_url = self.urlsConfig.get("jt1", {}).get("url", "").format(jid=jid)
            logging.info(f"[cleanUpJt] Parsing day type {jid} ({label}, get url {jt_json_url})...")
            try:
                rows = self.parseJson(jt_json_url, "jt1")  # This will download and parse the JSON for this journée type
            except OrthoAdl.OrthoADownloadError as e:
                # Log and skip this day type — don't abort the whole multi fetch
                logging.warning(f"[cleanUpJt] Skipping day type {jid}: {e}")
                continue
            if rows is not None:
                jtdata[label] = rows

        logging.info(f"[cleanUpJt] JT Done — {len(jtdata)} day types parsed")
        return jtdata


    def cleanUpCsv(self, dfin, structure_name):
        keys, _ = self._cfg(structure_name)
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

        if structure_name == "recette_jour":
            totals = {}
            for item in data:
                if str(item.get("Encaissé", "")).strip().lower() != "oui":
                    continue
                date = item.get("Réglé le", "")
                try:
                    amount = float(str(item.get("Montant", "0")).replace(",", "."))
                except ValueError:
                    amount = 0.0
                totals[date] = totals.get(date, 0.0) + amount
            data = [{"date": date, "amount": round(montant, 2)} for date, montant in sorted(totals.items())]

        if structure_name == "recettes_annuelles":
            totals = {}
            for item in data:
                date = item.get("Réglé le", "")
                try:
                    amount = float(str(item.get("Montant", "0")).replace(",", "."))
                except ValueError:
                    amount = 0.0
                totals[date] = totals.get(date, 0.0) + amount
            data = [{"date": date, "amount": round(montant, 2)} for date, montant in sorted(totals.items())]

        return data

    """
    This clean up is specific to config structure, a JSON file with a specific format, including Metatypes description and Fauteuils list
    The data cannot be retrieved with a single list of keys or subkeys as they're nested and several configs are included, hence the parsing must be hardcoded
    """
    def cleanUpMetatypesFauteuils(self, datain, structure_name):
        journees = datain

        sequences = journees["sequences"]
        metatypes_list = journees["enumerates"]["metatypes"]["list"]
        fauteuils_list = journees["enumerates"]["fauteuils"]["list"]

        out_struct = {}
        data = {}

        for key, roles in sequences.items():
            metatype_id = int(key.split("/")[-1])
            data[metatype_id] = roles.copy()

        for meta in metatypes_list:
            metatype_id = int(meta["name"].split("/")[-1])

            data.setdefault(metatype_id, {})
            data[metatype_id].update({
                "value": meta.get("value"),
                "duree": meta.get("duree"),
                "color": meta.get("color"),
            })

        out_struct["metatypes"] = data

        data = {}

        for item in fauteuils_list:
            fauteuil_id = int(item["name"])
            data.setdefault("fauteuils", {})
            data["fauteuils"][fauteuil_id] = {
                "value": item.get("value"),
            }

        out_struct["fauteuils"] = data

        return out_struct

    """
    Input data is a list of dicts, containing each : Nom, which is the user ID, Nom.1 = real name and Prénome.
    This clean up returns a list of dicts with only the user ID and the full name : "Prénom Nom.1"
    """
    def cleanUpUsers(self, dfin, structure_name):
        out_struct = []
        keys, _ = self._cfg(structure_name)

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

        keys, _ = self._cfg(structure_name)

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
        if structure_name in self.cleanUpSwitch:
            return self.cleanUpSwitch[structure_name](datain, structure_name)
        data_type = self.urlsConfig.get(structure_name, {}).get("type")
        if data_type in self.typeCleanUpSwitch:
            return self.typeCleanUpSwitch[data_type](datain, structure_name)
        return datain

def main():
        print("nothing to see here, just the OrthoAData module with its OrthoADataParse class")

        
if __name__ == "__main__":
    main()