import OrthoABase.OrthoAData as OrthoAData
import OrthoABase.OrthoAdl as OrthoAdl
import requests
import yaml
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

CONFIG_PATH = "OrthoABase/config.yaml"

def load_webhook():
    """
    Read the Discord webhook URL from config.yaml.
    Returns the URL string, or None if not set.
    """
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    return config.get("discord", {}).get("webhook") or None


def save_webhook(url):
    """
    Save the Discord webhook URL into config.yaml, preserving existing keys.
    """
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    config.setdefault("discord", {})["webhook"] = url

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, allow_unicode=True)


def ask_webhook_gui():
    """
    Open a small tkinter window asking the user to enter the Discord webhook URL.
    Saves it to config.yaml on confirmation.
    Returns the entered URL, or None if cancelled.
    """
    result = {"url": None}

    root = tk.Tk()
    root.title("Configuration Discord")
    root.resizable(False, False)

    # Center the window on screen
    root.update_idletasks()
    w, h = 480, 160
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(
        root,
        text="URL du webhook Discord non configurée.",
        font=("Arial", 11, "bold")
    ).pack(pady=(18, 2))

    tk.Label(
        root,
        text="Colle l'URL ci-dessous pour activer l'envoi des recettes :",
        font=("Arial", 10)
    ).pack()

    entry = tk.Entry(root, width=58)
    entry.pack(pady=8, padx=20)
    entry.focus()

    def on_confirm():
        url = entry.get().strip()
        if not url.startswith("https://discord.com/api/webhooks/"):
            messagebox.showerror(
                "URL invalide",
                "L'URL doit commencer par https://discord.com/api/webhooks/"
            )
            return
        save_webhook(url)
        result["url"] = url
        root.destroy()

    def on_skip():
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.pack()
    tk.Button(btn_frame, text="Enregistrer", command=on_confirm, width=14).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Ignorer", command=on_skip, width=14).pack(side="left", padx=8)

    root.mainloop()
    return result["url"]


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

    # Load webhook URL from config.yaml — ask user via GUI if not set
    webhook_url = load_webhook()
    if not webhook_url:
        webhook_url = ask_webhook_gui()

    if not webhook_url:
        print("[OrthoARecettes] Webhook Discord non configuré — envoi ignoré.")
        return

    payload = {"content": f"RX @ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}: {total:.2f}"}
    try:
        response = requests.post(webhook_url, json=payload)
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