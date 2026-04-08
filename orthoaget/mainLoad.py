from orthoaget.logger import setup_logger
from OrthoABase.OrthoAData import extract

def get_proth_records():
    data = extract(["prothesiste"])

    return data['prothesiste']


def get_users_records():
    data = extract(["users"])
    
    return data['users']

if __name__ == "__main__":
    full_data = get_proth_records()
    if full_data:
        for line in full_data:
            print(line)
