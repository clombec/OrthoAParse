from functools import reduce
from operator import getitem
from datetime import datetime
from urllib.parse import urlparse
from . import OrthoAdl
import logging
import os
import csv
import unicodedata
import pandas as pd
import json
from bs4 import BeautifulSoup
import re

class OrthoADataParse():
    def __init__(self, download_dir):
        self.orthoAdl = OrthoAdl.OrthoAdl(download_dir)  # raises OrthoAConnectionError if login fails
        self.cleanUpSwitch = {
            "MetatypesFauteuils": self.cleanUpMetatypesFauteuils,
            "users": self.cleanUpUsers,
            "alldaysyear": self.cleanUpJtYear,
            "jt": self.cleanUpJt,
            "JsonProth": self.cleanUpJsonProth,
        }
        self.typeCleanUpSwitch = {
            "csv": self.cleanUpCsv,
            "json": self.cleanUpJson,
        }
        self.urlsConfig = {}

    def end(self):
        self.orthoAdl.end()

    def parseHtmlForm(self, url: str) -> dict | None:
        """Navigate to url, parse its POST form fields, and return
        {"form_data": {...}, "form_display": {...}}, or None if redirected (session expired)."""
        from bs4 import BeautifulSoup
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self.orthoAdl.driver
        driver.get(url)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        if urlparse(driver.current_url).path.rstrip("/") != urlparse(url).path.rstrip("/"):
            return None

        soup = BeautifulSoup(driver.page_source, "html.parser")
        forms = soup.find_all("form")
        form = next(
            (f for f in forms if str(f.get("method", "")).lower() == "post"),
            forms[0] if forms else None,
        )
        if not form:
            raise RuntimeError(f"No form found at {url}")

        form_data: dict = {}
        form_display: dict = {}
        for tag in form.find_all("input"):
            name = tag.get("name")
            if not name:
                continue
            input_type = str(tag.get("type", "text")).lower()
            if input_type in ("checkbox", "radio"):
                if tag.has_attr("checked"):
                    form_data[name] = form_display[name] = tag.get("value", "on")
            elif input_type != "submit":
                form_data[name] = form_display[name] = tag.get("value", "")
        for tag in form.find_all("select"):
            name = tag.get("name")
            if not name:
                continue
            selected = tag.find("option", selected=True)
            opt = selected or tag.find("option")
            form_data[name] = opt.get("value", "") if opt else ""
            form_display[name] = opt.get_text(strip=True) if opt else ""
        for tag in form.find_all("textarea"):
            name = tag.get("name")
            if name:
                form_data[name] = form_display[name] = tag.get_text()

        patient_tag = soup.select_one("div.well ul.list-unstyled li a")
        if patient_tag:
            form_display["patient"] = patient_tag.get_text(strip=True)

        return {"form_data": form_data, "form_display": form_display}

    def postActDone(self, url: str, form_data: dict) -> bool:
        """Navigate to url and submit its form with form_data + done=1 via JavaScript."""
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self.orthoAdl.driver
        driver.get(url)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        merged = {**form_data, "done": "1"}
        driver.execute_script("""
            var form = document.querySelector('form');
            var data = arguments[0];
            for (var key in data) {
                var el = form.elements[key];
                if (el) {
                    el.value = data[key];
                } else {
                    var inp = document.createElement('input');
                    inp.type = 'hidden'; inp.name = key; inp.value = data[key];
                    form.appendChild(inp);
                }
            }
            form.submit();
        """, merged)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return True

    def parseCsv(self, csv_url, structure_name):
        rows = None
        csv_file = self.orthoAdl.downloadCsv(csv_url)  # raises OrthoADownloadError on failure
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
        self.orthoAdl.downloadPageHtml(html_url, htmlpage)  # raises OrthoADownloadError on failure
        html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                html_data = f.read()
                soup = BeautifulSoup(html_data, "html.parser")

            rows = self.cleanUp(soup, structure_name)

        return rows


    def parseHtmlPaginated(self, html_url: str, structure_name: str) -> list:
        """
        Fetch all pages of a paginated HTML browse-list table and return
        [{path, title}] for every row across all pages.

        path  — from <input type="checkbox" name="ids" value="...">
        title — from the column whose header contains "titre" (accent/case-insensitive)

        Pagination is detected via <a class="next page-link" href="..."> links.
        """
        all_items = []
        batch_start = 0
        title_col_idx = None

        while True:
            url = f"{html_url}?batch_start={batch_start}"
            htmlpage = "page_content.html"
            self.orthoAdl.downloadPageHtml(url, htmlpage)
            html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
            if not os.path.exists(html_file):
                break
            with open(html_file, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")

            table = soup.find("table", id="browse-list")
            if not table or not table.tbody:
                break

            if title_col_idx is None:
                headers = [th.get_text(strip=True) for th in table.thead.find_all("th")]
                title_col_idx = next(
                    (i for i, h in enumerate(headers)
                     if "titre" in unicodedata.normalize("NFD", h).encode("ascii", "ignore").decode().casefold()),
                    None,
                )
                if title_col_idx is None:
                    raise ValueError(f"[{structure_name}] No 'titre' column in headers: {headers}")

            for row in table.tbody.find_all("tr"):
                checkbox = row.find("input", {"type": "checkbox", "name": "ids"})
                if not checkbox:
                    continue
                path = checkbox.get("value", "")
                tds = row.find_all("td")
                if title_col_idx >= len(tds):
                    continue
                link = tds[title_col_idx].find("a")
                title = link.get_text(strip=True) if link else tds[title_col_idx].get_text(strip=True)
                if path and title:
                    all_items.append({"path": path, "title": title})

            next_link = soup.find("a", class_="next page-link")
            if not next_link or not next_link.get("href"):
                break
            batch_start += 50

        return all_items

    def _cfg(self, structure_name):
        cfg = self.urlsConfig.get(structure_name, {})
        keys = cfg.get("keys")
        if keys is not None:
            assert all(isinstance(k, list) for k in keys), \
                f"[{structure_name}] all keys must be lists, got: {keys}"
        return keys

    def _get_by_path(self, data, path: list):
        """
        Navigate a nested dict using a list of keys.
        Returns (field_name, value) where field_name is the last key in the path.
        The terminal value can be a scalar or a list.
        Example: ["user", "user_color"] -> ("user_color", "red")
        """
        return path[-1], reduce(getitem, path, data)

    def cleanUpJson(self, datain, structure_name):
        keys = self._cfg(structure_name)
        if not keys:
            return datain

        # Group keys by prefix (path minus last element)
        groups = {}
        for path in keys:
            prefix = tuple(path[:-1])
            groups.setdefault(prefix, []).append(path[-1])

        # Single prefix: navigate once, extract all fields
        if len(groups) == 1:
            prefix, fields = next(iter(groups.items()))
            obj = reduce(getitem, prefix, datain) if prefix else datain
            if isinstance(obj, list):
                return [{f: item.get(f) for f in fields} for item in obj]
            return {f: obj.get(f) for f in fields}

        # Multiple prefixes: flat dict, each path resolved independently
        def _safe_get(path, obj):
            for key in path:
                if isinstance(obj, list):
                    obj = obj[0] if obj else None
                if not isinstance(obj, dict):
                    return None
                obj = obj.get(key)
            return obj

        return {path[-1]: _safe_get(path, datain) for path in keys}

    """
        This clean up is specific to the JT structure :
        extracts data from json to get each Journée Type header
        Then launch downloand and parsing of the corresponding json for each journée type
    """
    def cleanUpJt(self, datain, structure_name):
        keys = self._cfg(structure_name)
        if not keys:
            return datain
        # Navigate to the list itself (strip the last field segment)
        first = keys[0]
        assert len(first) >= 1, f"[cleanUpJt] key path must not be empty, got {first}"
        list_path = first[:-1] if len(first) > 1 else first
        _, items = self._get_by_path(datain, list_path)
        if not isinstance(items, list):
            return items

        jtdata = {}
        for item in items:
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
        keys = self._cfg(structure_name)
        if keys is None:
            df_filtered = dfin  # no keys defined — keep all columns
        else:
            col_names = [k[0] for k in keys]
            df_filtered = dfin.loc[:, dfin.columns.intersection(col_names)]

        if isinstance(df_filtered, pd.Series):
            df_filtered = df_filtered.to_frame()

        data = df_filtered.to_dict(orient="records")

        if structure_name == "rdvs_history":
            for item in data:
                raw = item.pop("Date et heure du RDV", "")
                try:
                    item["Date et heure du RDV"] = datetime.strptime(raw, "%d/%m/%Y %Hh%M").isoformat()
                except (ValueError, TypeError):
                    item["Date et heure du RDV"] = raw or ""

        if structure_name == "prothesiste":
            for item in data:
                raw_rdv = item.pop("Date du rdv", "")
                try:
                    item["Date du rdv"] = datetime.fromisoformat(raw_rdv).isoformat()
                except (ValueError, TypeError):
                    item["Date du rdv"] = raw_rdv or ""
                pe_date_str = item.pop("PE", "") or ""
                try:
                    item["PE"] = datetime.fromisoformat(pe_date_str).isoformat() if pe_date_str else None
                except (ValueError, TypeError):
                    item["PE"] = None
                raw_envoi = item.pop("Date d'envoi au labo", "") or ""
                try:
                    item["Date d'envoi au labo"] = datetime.strptime(raw_envoi, "%d/%m/%Y").date().isoformat()
                except (ValueError, TypeError):
                    item["Date d'envoi au labo"] = raw_envoi
                raw_reception = item.pop("Date de réception", "") or ""
                try:
                    item["Date de réception"] = datetime.strptime(raw_reception, "%d/%m/%Y").date().isoformat()
                except (ValueError, TypeError):
                    item["Date de réception"] = raw_reception

        if structure_name == "echeances":
            for item in data:
                date_str = item.get("Date", "")
                try:
                    item["Date"] = datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
                except (ValueError, TypeError):
                    pass
                try:
                    item["Dû"] = float(str(item.get("Dû", "0")).replace(",", "."))
                except ValueError:
                    item["Dû"] = 0.0

        if structure_name == "recette_jour":
            totals = {}
            for item in data:
                if str(item.get("Encaissé", "")).strip().lower() != "oui":
                    continue
                date = item.get("Réglé le", "")
                try:
                    amount = float(str(item.get("Montant", "0")).replace(",", ".").replace(" ", ""))
                except ValueError:
                    amount = 0.0
                totals[date] = totals.get(date, 0.0) + amount
            data = [{"date": date, "amount": round(montant, 2)} for date, montant in sorted(totals.items())]

        return data

    """
    This clean up is specific to config structure, a JSON file with a specific format, including Metatypes description and Fauteuils list
    The data cannot be retrieved with a single list of keys or subkeys as they're nested and several configs are included, hence the parsing must be hardcoded
    """

    _MONTHS_FR = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }

    def _parseFrDatetime(self, label: str) -> str:
        """Parse "Lundi 3 Juin 2024 à 11:25" -> isoformat, or "" if unparseable."""
        if not label or not isinstance(label, str):
            return ""
        m = re.search(r"(\d+)\s+(\w+)\s+(\d{4})\s+à\s+(\d{1,2}):(\d{2})", label, re.IGNORECASE)
        if not m:
            return ""
        month = self._MONTHS_FR.get(m.group(2).lower())
        if month is None:
            return ""
        return datetime(int(m.group(3)), month, int(m.group(1)),
                        int(m.group(4)), int(m.group(5))).isoformat()

    def cleanUpJsonProth(self, datain, structure_name):
        """
        Parse the JsonProth paginated JSON into a list of prothesiste records.
        Column positions are derived from datain["columns"] — no hardcoded indices.
        Each record mirrors the prothesiste CSV output and adds:
          'abspath'     : act URL path (/medical/prothesiste/<hash>)
          'patient_url' : clinique link for the patient
        """
        # Build col_name -> index from the columns descriptor
        col_idx = {col["name"]: i for i, col in enumerate(datain.get("columns", []))}

        def cell(row, name):
            i = col_idx.get(name)
            return row[i] if i is not None and i < len(row) else {}

        result = []
        for line in datain.get("lines", []):
            rows = line.get("rows", [])

            pe_raw = cell(rows, "pe").get("value", "")
            de_raw = cell(rows, "send_date").get("value", "")
            dr_raw = cell(rows, "receipt_date").get("value", "")
            try:
                pe_iso = datetime.strptime(pe_raw, "%d/%m/%Y %Hh%M").isoformat() if pe_raw else None
            except (ValueError, TypeError):
                pe_iso = None
            try:
                de_iso = datetime.strptime(de_raw, "%d/%m/%Y").date() if de_raw else None
            except (ValueError, TypeError):
                de_iso = None
            try:
                dr_iso = datetime.strptime(dr_raw, "%d/%m/%Y").date() if dr_raw else None
            except (ValueError, TypeError):
                dr_iso = None

            result.append({
                "Prothésiste":          cell(rows, "prothesiste").get("value", ""),
                "Patient":              cell(rows, "user_abspath").get("title", ""),
                "Date du rdv":          self._parseFrDatetime(cell(rows, "acte_dtime").get("title", "")),
                "Acte prothésiste":     cell(rows, "acte_prothesiste").get("title", ""),
                "Date d'envoi au labo": de_iso,
                "Date de réception":    dr_iso,
                "PE":                   pe_iso,
                "Durée":                cell(rows, "duree").get("value", ""),
                "Commentaires":         cell(rows, "comment").get("value", ""),
                "abspath":              line.get("abspath", ""),
                "patient_url":          cell(rows, "user_abspath").get("link", ""),
            })
        return result

    def parseJsonPaginated(self, json_url: str, structure_name: str) -> list:
        """Fetch all pages of a paginated JSON endpoint and return concatenated results."""
        all_lines = []
        columns = None
        url = f"{self.orthoAdl.OrthoAUrlBase}/{json_url}"
        while url:
            self.orthoAdl.downloadPageText(url, fullUrl=True)
            json_file = os.path.join(self.orthoAdl.download_dir, "page_content.txt")
            if not os.path.exists(json_file):
                break
            with open(json_file, "r", encoding="utf-8") as f:
                page_data = json.load(f)
            if columns is None:
                columns = page_data.get("columns", [])
            all_lines.extend(page_data.get("lines", []))
            url = page_data.get("pagination", {}).get("next", "")
            logging.info(f"[parseJsonPaginated] {len(all_lines)} records, next={url}")
        return self.cleanUp({"columns": columns or [], "lines": all_lines}, structure_name)

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
        keys = self._cfg(structure_name)

        if keys is None:
            logging.error(f"Error: dataKeys for {structure_name} is not defined")
            return out_struct

        col_names = [k[0] for k in keys]
        df_filtered = dfin.loc[:, col_names]

        if isinstance(df_filtered, pd.Series):
            df_filtered = df_filtered.to_frame()

        df_records = df_filtered.to_dict(orient="records")

        patientId = col_names[0]
        lastName = col_names[1]
        firstName = col_names[2]

        for user in df_records:
            user_id = user.get(patientId)
            out_struct.append({
                "id": user_id,
                "last_name": user.get(lastName),
                "first_name": user.get(firstName),
            })
        return out_struct

    """
    This clean up is specific to the JT2026 structure, which is an HTML table with a specific format. It extracts the relevant columns based on the keys defined in url.yaml for this structure, and returns a list of lists containing the cleaned data.
    It is base don a beautiful soup object, which is passed to the cleanUp function
    """
    def cleanUpJtYear(self, soupin, structure_name):
        out_struct = []

        # Get the html table with id "browse-list"
        table = soupin.find('table', id='browse-list')

        # get the headers of the table
        headers = [th.get_text(strip=True) for th in table.thead.find_all('th')]

        keys = self._cfg(structure_name)

        if keys is None:
            logging.error(f"Error: dataKeys for {structure_name} is not defined")
            return out_struct

        col_names = [k[0] for k in keys]
        indexes = [headers.index(col) for col in col_names]

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