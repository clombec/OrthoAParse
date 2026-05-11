import json
from OrthoABase.OrthoAData import main
from orthoaget.session import OrthoASession
from orthoaget.logger import setup_logger
from datetime import datetime


if __name__ == "__main__":
    setup_logger()

    with OrthoASession() as session:
        data = session.extract(
            ["jt", "rdvs_all", "MetatypesFauteuils"],
            params={"year": datetime.now().strftime("%Y")})
        with open("toto.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
#    main()
