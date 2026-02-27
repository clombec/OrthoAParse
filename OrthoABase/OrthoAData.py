import datetime
from . import OrthoAdl
import os
import csv
import pandas as pd
from . import DownloadDir
import json
import yaml
from bs4 import BeautifulSoup
from datetime import datetime
import re

DEBUG_NO_DL = False

class OrthoADataParse():
    def __init__(self, download_dir):
        if DEBUG_NO_DL:
            self.orthoAdl = OrthoAdl.OrthoAdl(download_dir, no_dl=True)
        else:
            self.orthoAdl = OrthoAdl.OrthoAdl(download_dir)
        self.cleanUpSwitch = {
            "rdvs_history": self.cleanUpCsv,
            "jt": self.cleanUpCalendarEvents,
            "metatypes": self.cleanUpMetatypes,
            "users": self.cleanUpUsers,
            "alldays2026": self.cleanUpJt2026,
            "prothesiste": self.cleanUpCsv
        }
        self.dataKeys = {}

    def end(self):
        self.orthoAdl.end()
    
    def parseCsv(self, csv_url, structure_name):
        rows = None
        if not DEBUG_NO_DL:
            self.orthoAdl.downloadCsv(csv_url)
        # Implement CSV parsing logic here
        csv_file = os.path.join(self.orthoAdl.download_dir, "export.csv")
        if os.path.exists(csv_file):
#            df = pd.read_csv(csv_file, encoding="utf-8")
            df = pd.read_csv(
                csv_file,
                encoding="utf-8",
                sep=";",
                quotechar='"',
                quoting=csv.QUOTE_ALL,   # ou QUOTE_MINIMAL selon ton fichier
                engine="python"          # plus tolérant que le moteur C
            )

            rows = self.cleanUp(df, structure_name)

        return rows

    def parseJson(self, json_url, structure_name):
        rows = None
        if not DEBUG_NO_DL:
            self.orthoAdl.downloadPageText(json_url)
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
        if not DEBUG_NO_DL:
            self.orthoAdl.downloadPageHtml(html_url, htmlpage)
        html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                html_data = f.read()
                soup = BeautifulSoup(html_data, "html.parser")

            rows = self.cleanUp(soup, structure_name)                

        return rows
    
    def parseMulti(self, html_url, structure_name):
        outdata = None
        htmlpage = "page_content.html"
        if not DEBUG_NO_DL:
            self.orthoAdl.downloadPageHtml(html_url, htmlpage)
        html_file = os.path.join(self.orthoAdl.download_dir, htmlpage)
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                html_data = f.read()
            soup = BeautifulSoup(html_data, "html.parser")

                        # Trouver tous les liens
            links = soup.find_all('a', href=True)

            # Filtrer et afficher les liens et le texte associé
            for link in links:
                href = link['href']
                if 'planning/jt/journees/' in href:
                    print(f"Lien: {href}")
                    # Search for the first integer in the string
                    if type(href) == str:
                        match = re.search(r'\d+', href)
                        if match:
                            last_number = int(match.group())
                            print(last_number)  # Output: 12

                

                    #outdata = self.cleanUp(soup, structure_name)                

        return outdata
    
    def specific_filter(self, data, structure_name):
        if structure_name == "rdvs_history":
            for item in data:
                dt = datetime.strptime(
                    item.pop("Date et heure du RDV"),
                    "%d/%m/%Y %Hh%M"
                )
                item["Date et heure du RDV"] = dt.isoformat()

        if structure_name == "prothesiste":
            for item in data:
                dt = datetime.fromisoformat(
                    item.pop("Date du rdv"),
                )
                item["Date du rdv"] = dt.isoformat()
        return data
    
    def cleanUpCsv(self, dfin, structure_name):
        keys = self.dataKeys.get(structure_name)
        df_filtered = dfin.loc[:, dfin.columns.intersection(keys)]

        if isinstance(df_filtered, pd.Series):
            df_filtered = df_filtered.to_frame()

        dataout = self.specific_filter(df_filtered.to_dict(orient="records"), structure_name)

        return dataout


    """

    """
    def cleanUpCalendarEvents(self, datain, structure_name):
        events = datain["events"]
        keys = self.dataKeys.get(structure_name)

        #To avoid not subscriptable error if keys is not defined or not a list/tuple
        if keys is None or not isinstance(keys, (list, tuple)): 
            print(f"Error: dataKeys for {structure_name} is not subscriptable")
            return []
        
        # Filter data from input based on keys defined in url.yaml for this structure
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
            print(f"Error: dataKeys for {structure_name} is not subscriptable")
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
        lastName = keys[1]  # Assuming the second key is the last name
        firstName = keys[2]  # Assuming the third key is the first name

        for user in df_records:
            # Create out structure with only the user ID and the full name "Prénom Nom"
            out_struct.append({
                "id": user.get(patientId),  # Assuming the first key is the user ID
                "name": f"{user.get(firstName)} {user.get(lastName)}" # Assuming the second key is the last name and the third key is the first name
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
            print(f"Error: dataKeys for {structure_name} is not subscriptable")
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


"""
Get all data from OrthoAdvance, parse it and save it in a structured format (e.g. CSV, JSON, database)
"""
def extract(urlFile="url.yaml"):    # Configurer le dossier de téléchargement
    if not DEBUG_NO_DL:
        download_dir = DownloadDir.setupDownloadDir("downloads")
    else:
        download_dir = DownloadDir.setupDownloadDir("downloads", noclean=True)
    orthoAdp = OrthoADataParse(download_dir)

    # Load configuration from url.yaml
    with open(urlFile, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Parse each structure and store results
    parsed_data = {}
    for structure_name, structure_config in config.items():
        url = structure_config.get("url")
        data_type = structure_config.get("type")
        keys = structure_config.get("keys", None)
        orthoAdp.dataKeys[structure_name] = keys

        data = None
        if data_type == "csv":
            data = orthoAdp.parseCsv(url, structure_name)
        elif data_type == "json":
            data = orthoAdp.parseJson(url, structure_name)
        elif data_type == "html":
            data = orthoAdp.parseHtml(url, structure_name)
        elif data_type == "multi":
            data = orthoAdp.parseMulti(url, structure_name)

        if data is not None:
            parsed_data[structure_name] = data

    orthoAdp.end()

    return parsed_data

if __name__ == "__main__":
    OrthoAdata = extract()
    with open("data.json", "w") as f:
        json.dump(OrthoAdata, f, indent=2)

    for rdv in OrthoAdata["rdvs_history"]:
        patient_name = rdv.get("Patient")
        user = next((u for u in OrthoAdata["users"] if u["name"].lower() == patient_name.lower()), None)
        if user:
            patient_id = user["id"]
            print(f"Rendez-vous for patient {patient_name} (ID: {patient_id})")
        else:
            print(f"Rendez-vous for patient {patient_name} (ID: not found)")
    #print(OrthoAdata)