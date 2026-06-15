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

        # Test tri alphabétique des libellés photos
        sorted_items = session.sort_html_table_items("PhotosLibelles")
        print(f"{len(sorted_items)} libellés triés :")
        for item in sorted_items:
            print(f"  {item['title']}")

#    main()
