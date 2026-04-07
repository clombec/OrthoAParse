from importlib.resources import files

from orthoaget.logger import setup_logger
from OrthoABase.OrthoAData import extract

def get_records():
    yaml_path = files("OrthoABase") / "prothData.yaml"
    data = extract(str(yaml_path))

    full_data = data['prothesiste']
    patient_ids = data['users']

    for line in full_data:
        patient_name = line.get("Patient", "")
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
