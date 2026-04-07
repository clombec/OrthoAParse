import sys
from pathlib import Path

from orthoaget import PROJECT_ROOT
from orthoaget.logger import setup_logger

# Root of OrthoAGet project (two levels up from mainLoad.py)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
    
from OrthoABase.OrthoAData import extract

def get_records():
    data = extract(f"{PROJECT_ROOT}/OrthoAProthData/prothData.yaml")

    full_data = data['prothesiste']
    patient_ids = data['users']

    for line in full_data:
        patient_name = line.get("Patient", "")
        # Map each patient in the act list to a URL from patient lookup table by case-insensitive name match
        for id in patient_ids:
            if id["name"].lower() == patient_name.lower():
                line["url"] = f"{id['url']}" 
                break
    return full_data

if __name__ == "__main__":
    full_data = get_records()
    if full_data:
        for line in full_data:
            print(line)

