import OrthoABase.OrthoAData as OrthoAData
import requests
from datetime import datetime

# Discord Webhook URL - Comes from OrthoARecettes/discord_webhook.txt file
# OrthoARecettes/discord_webhook_example.txt should be renamed to discord_webhook.txt and contain the actual webhook URL for this to work
with open("OrthoARecettes/discord_webhook.txt", "r") as f:
    DISCORD_WEBHOOK_URL = f.read()

def main():
    data = OrthoAData.extract(
        "OrthoARecettes/recettes.yaml"
    )
    total = 0
    for line in data["recette"]:
        amount = line["Montant"]
        canceled = line["A"]
        if not canceled:
            total = total + float(amount.replace(",", "."))
            print(f"Recette: {amount}")
    print(f"Total: {total:.2f}")

    data = {"content": f"RX @ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}: {total:.2f}"}
    requests.post(DISCORD_WEBHOOK_URL, json=data)
# =========================
# Start
# =========================
if __name__ == "__main__":
    main()
