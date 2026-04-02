"""
app_web.py

Simple Flask web app — exposes a single button to trigger OrthoARecettes.main().
Run with: python app_web.py
Access on the local network at: http://<IP_DU_PC>:5000
"""

from flask import Flask, render_template, redirect, url_for
import logging
import OrthoABase.OrthoALogger as OrthoALogger
import OrthoARecettes.OrthoARecettes as OrthoARecettes

app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    message = ("success", "✅ succès.")
    return render_template("index.html", message=message)


@app.route("/recettes", methods=["POST"])
def recettes():
    """Trigger OrthoARecettes.main() and redirect back to index with a status message."""
    try:
        amount = OrthoARecettes.main(oneshot=True)
        message = ("success", f"✅ Envoyé avec succès : {amount:.2f}")
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution des recettes : {e}")
        message = ("error", f"❌ Erreur : {e}")

    return render_template("index.html", message=message)

def main():
    # host="0.0.0.0" makes the server accessible from other machines on the network
    app.run(host="0.0.0.0", port=5001, debug=False)


if __name__ == "__main__":
    main()