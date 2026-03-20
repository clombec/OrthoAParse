import OrthoABase.OrthoAData as OrthoAData
import OrthoABase.OrthoAdl as OrthoAdl
import requests
from datetime import datetime

# Discord Webhook URL - Comes from OrthoARecettes/discord_webhook.txt file
# OrthoARecettes/discord_webhook_example.txt should be renamed to discord_webhook.txt and contain the actual webhook URL for this to work
with open("OrthoARecettes/discord_webhook.txt", "r") as f:
    DISCORD_WEBHOOK_URL = f.read()

def main():
    try:
        data = OrthoAData.extract(
            "OrthoARecettes/recettes.yaml"
        )
    except OrthoAdl.OrthoAConnectionError as e:
        print(f"[OrthoARecettes] Erreur de connexion à OrthoAdvance : {e}")
        return
    except OrthoAdl.OrthoADownloadError as e:
        print(f"[OrthoARecettes] Erreur de téléchargement : {e}")
        return
    except Exception as e:
        print(f"[OrthoARecettes] Erreur inattendue lors de la récupération des données : {e}")
        return

    total = 0
    for line in data["recette"]:
        amount = line["Montant"]
        canceled = line["A"]
        if not canceled:
            total = total + float(amount.replace(",", "."))
            print(f"Recette: {amount}")
    print(f"Total: {total:.2f}")

    data = {"content": f"RX @ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}: {total:.2f}"}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        print(f"[OrthoARecettes] Impossible de joindre Discord (réseau) : {e}")
    except requests.exceptions.HTTPError as e:
        print(f"[OrthoARecettes] Erreur HTTP Discord (webhook invalide ?) : {e}")
    except requests.exceptions.RequestException as e:
        print(f"[OrthoARecettes] Erreur lors de l'envoi Discord : {e}")

# =========================
# Start
# =========================
if __name__ == "__main__":
    main()