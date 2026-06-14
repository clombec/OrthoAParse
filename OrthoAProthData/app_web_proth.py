"""
app_web_proth.py

Flask web app for prothesiste actes management.
Run with: python app_web_proth.py
Access at: http://localhost:5002
"""

from flask import Flask, render_template, request, jsonify, url_for
import yaml
import logging
from datetime import datetime, date
import OrthoABase.OrthoAdl as OrthoAdl
from orthoaget.session import OrthoASession
from orthoaget.logger import setup_logger
from orthoaget import PROJECT_ROOT

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, s-maxage=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

class ProthDataManager:
    def __init__(self):
        self.full_data = []
        self.filtered_data = []
        self.color_map = {}
        self.column_map = {}
        self.selected_actes = set()
        self.current_sort_column = None
        self.current_sort_reverse = False
        self.today_tx_filter_active = False
        self.today_rx_filter_active = False
        self.proth_filter = "Tous"
        self.set_done = None  # callable(acte_urls) captured from session

    def load_data(self):
        """Load data from OrthoAData and configuration."""
        try:
            with open(f"{PROJECT_ROOT}/OrthoAProthData/Configuration.yaml", "r", encoding="utf-8") as f:
                yamlconfig = yaml.safe_load(f)
                self.color_map = yamlconfig.get("colors", {})
                self.column_map = yamlconfig.get("columns", {})
        except FileNotFoundError:
            self.color_map = {}
            self.column_map = {}

        try:
            with OrthoASession() as session:
                self.full_data = session.get_proth_records()
                self.set_done = session.make_proth_set_done()

            logging.info(f"Data loaded. {len(self.full_data)} records found.")
            return True
        except Exception as e:
            logging.error(f"Error loading data: {e}")
            return False

    def apply_filters(self):
        """Apply current filters to data."""
        proth_value = self.proth_filter
        self.filtered_data = []
        today_str = date.today().isoformat()

        for row in self.full_data:
            if proth_value != "Tous" and row["Prothésiste"] != proth_value:
                continue

            if self.selected_actes and row["Acte prothésiste"] not in self.selected_actes:
                continue

            if self.today_tx_filter_active:
                try:
                    my_date = datetime.strptime(row["Date d'envoi au labo"], "%d/%m/%Y").date()
                    if my_date.isoformat() != today_str:
                        continue
                except (ValueError, KeyError):
                    continue

            if self.today_rx_filter_active:
                try:
                    my_date = datetime.strptime(row["Date de réception"], "%d/%m/%Y").date()
                    if my_date.isoformat() != today_str:
                        continue
                except (ValueError, KeyError):
                    continue

            self.filtered_data.append(row)

        self.apply_sort()

    def apply_sort(self):
        """Apply current sorting to filtered data."""
        if not self.current_sort_column:
            return

        col = self.current_sort_column

        def try_parse(value):
            """Convert values for stable sorting."""
            if col in ["Date d'envoi au labo", "Date de réception"]:
                if not value:
                    return datetime.min
                try:
                    return datetime.strptime(value, "%d/%m/%Y %H:%M")
                except ValueError:
                    try:
                        return datetime.strptime(value, "%d/%m/%Y")
                    except ValueError:
                        return datetime.min

            try:
                return float(value)
            except (ValueError, TypeError):
                pass

            return str(value).lower()

        self.filtered_data.sort(
            key=lambda x: try_parse(x.get(col, "")),
            reverse=self.current_sort_reverse
        )

    def get_proth_values(self):
        """Get unique prosthetist values."""
        return sorted(set(d["Prothésiste"] for d in self.full_data))

    def get_acte_values(self):
        """Get unique acte values."""
        return sorted(set(d["Acte prothésiste"] for d in self.full_data))

    def update_filters_from_request(self, request_data):
        """Update filters from AJAX request data."""
        self.proth_filter = request_data.get('proth_filter', 'Tous')
        self.selected_actes = set(request_data.get('selected_actes', []))
        self.today_tx_filter_active = request_data.get('today_tx_filter', False)
        self.today_rx_filter_active = request_data.get('today_rx_filter', False)
        self.current_sort_column = request_data.get('sort_column')
        self.current_sort_reverse = request_data.get('sort_reverse', False)

# Global data manager instance
data_manager = ProthDataManager()

@app.route("/")
def index():
    """Main page - show empty interface while client-side JavaScript loads data."""
    return render_template(
        "proth_index.html",
        proth_values=["Tous"],
        acte_values=[],
        color_map={},
        data=[],
        columns=[]
    )

@app.route("/filter", methods=["POST"])
def filter_data():
    """AJAX endpoint for filtering and sorting."""
    if not data_manager.full_data:
        if not data_manager.load_data():
            return jsonify({'success': False, 'error': 'Impossible de charger les données'}), 500

    request_data = request.get_json()
    data_manager.update_filters_from_request(request_data)
    data_manager.apply_filters()

    return jsonify({
        'success': True,
        'data': data_manager.filtered_data,
        'count': len(data_manager.filtered_data),
        'proth_values': ["Tous"] + data_manager.get_proth_values(),
        'acte_values': data_manager.get_acte_values(),
        'color_map': data_manager.color_map,
        'columns': list(data_manager.full_data[0].keys()) if data_manager.full_data else []
    })

@app.route("/save_colors", methods=["POST"])
def save_colors():
    """Save color configuration."""
    colors = request.get_json().get('colors', {})
    data_manager.color_map = colors

    config = {
        "colors": data_manager.color_map,
        "columns": data_manager.column_map
    }

    try:
        with open(f"{PROJECT_ROOT}/OrthoAProthData/Configuration.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route("/set_actes_as_done", methods=["POST"])
def route_set_actes_as_done():
    """Mark one or more acts as done. Expects JSON body: {"urls": ["<full_acte_url>", ...]}"""
    body = request.get_json(silent=True) or {}
    acte_urls = body.get("urls", [])
    if not acte_urls:
        return jsonify({'success': False, 'error': 'No URLs provided'}), 400
    if not data_manager.set_done:
        return jsonify({'success': False, 'error': 'Session expirée, veuillez rafraîchir'}), 401
    try:
        data_manager.set_done(acte_urls)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"[set_actes_as_done] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/refresh")
def refresh():
    """Refresh data."""
    if data_manager.load_data():
        data_manager.apply_filters()
        return jsonify({'success': True, 'count': len(data_manager.filtered_data)})
    else:
        return jsonify({'success': False, 'error': 'Erreur de chargement'})

def main():
    setup_logger()
    app.run(host="0.0.0.0", port=5002, debug=False)

if __name__ == "__main__":
    main()