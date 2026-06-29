import json
#from OrthoABase.OrthoAData import main
from orthoaget.session import OrthoASession
from orthoaget.logger import setup_logger
from datetime import datetime


if __name__ == "__main__":
    setup_logger()

    with OrthoASession(get_all_user_data=True) as session:
        data = session.get_anonymized_data()
#        data = session.get_user_rdv_records()

        with open("outdata/stats.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


