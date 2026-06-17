import json
from OrthoABase.OrthoAData import main
from orthoaget.session import OrthoASession
from orthoaget.logger import setup_logger
from datetime import datetime


if __name__ == "__main__":
    setup_logger()

    with OrthoASession() as session:
#        data = session.get_stats_records()
#        data = session.extract(
#            ["users", "rdvs_all", "MetatypesFauteuils"],
#            params = {"year": datetime.now().strftime("%Y")})
#        data = session.extract(
#            ["rdvs_history"],
#            params={"year": datetime.now().strftime("%Y")})
#        with open("toto.json", "w", encoding="utf-8") as f:
#            json.dump(data, f, ensure_ascii=False, indent=4)

        # Test échéances
#        now = datetime.now()
#        dayin  = datetime(now.year - 2, 1, 1).strftime("%Y-%m-%d")
#        dayout = now.strftime("%Y-%m-%d")
#        echeances = session.get_echeances_records(dayin, dayout)
#        print(f"{len(echeances)} échéances récupérées")
#        total = sum(item.get("Dû", 0.0) for item in echeances)
#        print(f"Total dû : {round(total, 2)} €")

        data = session.get_proth_records()

#    main()
