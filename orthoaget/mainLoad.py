from orthoaget.logger import setup_logger
from OrthoABase.OrthoAData import extract

def get_proth_records():
    data = extract(["prothesiste", "users"])

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
    full_data = get_proth_records()
    if full_data:
        for line in full_data:
            print(line)
