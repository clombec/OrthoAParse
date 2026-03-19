import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import yaml
from datetime import datetime, date
import OrthoABase.OrthoAData as OrthoAData
import OrthoABase.OrthoAdl as OrthoAdl
from tkinter import colorchooser
import platform
import webbrowser


# =========================
# Application
# =========================
class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Actes Prothésiste")
        self.geometry("900x500")
        self.iconbitmap("OrthoAProth.ico")
        self.click_str = "▶▶ Ouvrir dans OrthoAdvance "

        self.full_data = []
        self.filtered_data = []

        self.selected_actes = set()
        self.sort_reverse = False
        self.today_tx_filter_active = False
        self.today_rx_filter_active = False

        self.create_filters()
        self.create_table()

        self.show_loading()
        self.after(100, self.load_data)

        self.current_sort_column = None
        self.current_sort_reverse = False

    def show_loading(self):

        # Désactive table
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Overlay
        self.loading_frame = ctk.CTkFrame(self)
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.loading_label = ctk.CTkLabel(
            self.loading_frame,
            text="Récupération des données...",
            font=("Arial", 20)
        )
        self.loading_label.pack(padx=40, pady=40)

        self.update_idletasks()

    def hide_loading(self):
        if hasattr(self, "loading_frame"):
            self.loading_frame.destroy()

    def load_data(self):

        with open("OrthoAProthData/Configuration.yaml", "r", encoding="utf-8") as f:
            global COLOR_MAP, COLUMN_MAP
            yamlconfig = yaml.safe_load(f)
            COLOR_MAP = yamlconfig.get("colors", {})
            COLUMN_MAP = yamlconfig.get("columns", {})

        data = OrthoAData.extract(
            "OrthoAProthData/prothData.yaml"
        )
        self.full_data = data['prothesiste']
        self.patientIds = data['users']

        for line in self.full_data:
            patient_name = line.get("Patient", "")
            for id in self.patientIds:
                if id["name"].lower() == patient_name.lower():
                    line["url"] = f"{self.click_str}{id['url']}"
                    break

        
        print(f"Data loaded at {datetime.now().strftime('%H:%M:%S')}. {len(self.full_data)} records found.")

        self.setup_columns()
        self.update_filters()

        self.apply_filters()

        self.hide_loading()

        print(f"Data processing complete at {datetime.now().strftime('%H:%M:%S')}. Table populated with {len(self.filtered_data)} records.")
        
    # =========================
    # Filtres
    # =========================
    def create_filters(self):

        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=10, pady=10)

        self.proth_filter = ctk.CTkComboBox(
            frame,
            values=["Tous"],
            command=self.apply_filters,
            width=180
        )
        self.proth_filter.set("Tous")
        self.proth_filter.pack(side="left", padx=10)

        self.acte_values = []

        self.acte_button = ctk.CTkButton(
            frame,
            text="Choisir actes",
            command=self.open_acte_menu,
            width=180
        )
        self.acte_button.pack(side="left", padx=10)

        # Bouton Envoi Aujourd'hui
        self.today_tx_button = ctk.CTkButton(
            frame,
            text="Envoi Aujourd'hui",
            command=self.toggle_today_tx_filter,
            width=150
        )
        self.today_tx_button.pack(side="left", padx=10)
        self.default_today_color = self.today_tx_button.cget("fg_color")

        # Bouton Reception Aujourd'hui
        self.today_rx_button = ctk.CTkButton(
            frame,
            text="Reception Aujourd'hui",
            command=self.toggle_today_rx_filter,
            width=150
        )
        self.today_rx_button.pack(side="left", padx=10)

        # Bouton Rafraîchir
        self.refresh_button = ctk.CTkButton(
            frame,
            text="Rafraîchir",
            command=self.refresh,
            width=150
        )
        self.refresh_button.pack(side="left", padx=10)

        # Compteur
        self.counter_label = ctk.CTkLabel(frame, text="")
        self.counter_label.pack(side="right", padx=10)

        self.color_button = ctk.CTkButton(
            frame,
            text="Couleurs actes",
            command=self.open_color_manager,
            width=160
        )
        self.color_button.pack(side="left", padx=10)

    def update_filters(self):

        if not self.full_data:
            return

        proth_values = sorted(
            set(d["Prothésiste"] for d in self.full_data)
        )

        acte_values = sorted(
            set(d["Acte prothésiste"] for d in self.full_data)
        )

        # Mise à jour combo prothésiste
        self.proth_filter.configure(
            values=["Tous"] + proth_values
        )

        # Mise à jour liste actes
        self.acte_values = acte_values
        
    # =========================
    # Menu couleurs
    # =========================
    def open_color_manager(self):

        self.color_window = tk.Toplevel(self)
        self.color_window.title("Gestion des couleurs des actes")
        self.color_window.geometry("450x550")
        self.color_window.grab_set()

        # ===== FRAME PRINCIPALE =====
        main_frame = tk.Frame(self.color_window)
        main_frame.pack(fill="both", expand=True)

        # ===== CANVAS SCROLLABLE =====
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)

        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ===== SCROLL MOLETTE SOURIS =====
        def _on_mousewheel(event):
            system = platform.system()

            if system == "Windows":
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            elif system == "Darwin":
                canvas.yview_scroll(int(-1 * event.delta / 2), "units")

            else:  # Linux
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")


        # Windows & Mac
        canvas.bind("<MouseWheel>", _on_mousewheel)

        # Linux
        canvas.bind("<Button-4>", _on_mousewheel)
        canvas.bind("<Button-5>", _on_mousewheel)

        # ===== CONTENU =====
        self.temp_colors = COLOR_MAP.copy()
        self.color_squares = {}

        for acte in sorted(self.temp_colors.keys()):

            row = tk.Frame(scrollable_frame)
            row.pack(fill="x", pady=5, padx=10)

            square = tk.Label(
                row,
                bg=self.temp_colors[acte],
                width=3,
                height=1,
                relief="ridge",
                cursor="hand2"
            )
            square.pack(side="left", padx=10)

            square.bind("<Button-1>",
                        lambda e, a=acte: self.choose_color(a))

            label = tk.Label(row, text=acte, anchor="w")
            label.pack(side="left", fill="x", expand=True)

            self.color_squares[acte] = square

        # ===== BOUTONS FIXES EN BAS =====
        button_frame = tk.Frame(self.color_window)
        button_frame.pack(fill="x", pady=10)

        tk.Button(button_frame, text="OK",
                command=self.save_colors).pack(side="left", padx=20)

        tk.Button(button_frame, text="Annuler",
                command=self.color_window.destroy).pack(side="left", padx=20)
        
    def choose_color(self, acte):

        color_code = colorchooser.askcolor(
            title=f"Choisir couleur pour {acte}"
        )

        if color_code[1]:  # si pas annulé
            self.temp_colors[acte] = color_code[1]
            self.color_squares[acte].configure(bg=color_code[1])
                
    def save_colors(self):

        global COLOR_MAP, COLUMN_MAP

        COLOR_MAP = self.temp_colors.copy()
        #COLUMN_MAP = self.temp_columns.copy()

        with open("OrthoAProthData/configuration.yaml", "w", encoding="utf-8") as f:
            config = {
                "colors": COLOR_MAP,
                "columns": COLUMN_MAP
            }
            yaml.dump(config, f, allow_unicode=True)

        self.color_window.destroy()

        # Recharger couleurs dans table
        self.populate_table()

    # =========================
    # Table
    # =========================
    def create_table(self):

        self.tree = ttk.Treeview(self, show="headings")
        self.tree.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self, orient="vertical",
                                command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")

        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind("<Double-1>", self.on_double_click)

        self.tree.bind("<Button-1>", self.on_click)

        self.tree.bind("<Motion>", self.on_hover)

    def on_hover(self, event):

        column = self.tree.identify_column(event.x)

        if column:
            col_index = int(column.replace("#", "")) - 1
            col_name = self.tree["columns"][col_index]

            if col_name == "url":
                self.tree.configure(cursor="hand2")
            else:
                self.tree.configure(cursor="")
                
    def on_click(self, event):

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item or not column:
            return

        col_index = int(column.replace("#", "")) - 1
        col_name = self.tree["columns"][col_index]

        if col_name == "url":
            value = self.tree.item(item)["values"][col_index].replace(self.click_str, "")

            if value:
                webbrowser.open(value)

    def setup_columns(self):
        global COLUMN_MAP

        if not self.full_data:
            return

        columns = list(self.full_data[0].keys())

        self.tree["columns"] = columns

        for col in columns:
            self.tree.heading(
                col,
                text=col,
                command=lambda c=col: self.sort_column(c)
            )
            ww = COLUMN_MAP.get(col, {}).get("width", 170)
            self.tree.column(col, width=ww, anchor="center")

    # =========================
    # Remplissage table
    # =========================
    def populate_table(self):

        for row in self.tree.get_children():
            self.tree.delete(row)

        for row_data in self.filtered_data:

            values = []
            max_lines = 1

            for key, value in row_data.items():

                if key == "Commentaires" and value:
                    text = str(value).replace("\\n", "\n")
                    values.append(text)
                    lines = text.count("\n") + 1
                    max_lines = max(max_lines, lines)
                elif key == "Date du rdv":
                    dt = datetime.fromisoformat(value)
                    values.append(dt.strftime("%d/%m/%Y %H:%M"))
                elif key == "PE":
                    try:
                        dt = datetime.fromisoformat(value)
                        values.append(dt.strftime("%d/%m/%Y %H:%M"))
                    except (ValueError, TypeError):
                        values.append("")
                else:
                    values.append(value)

            tag = row_data["Acte prothésiste"]

            item_id = self.tree.insert("", "end", values=values, tags=(tag,))

            # Couleur acte
            if tag in COLOR_MAP:
                self.tree.tag_configure(tag, background=COLOR_MAP[tag])
            else:
                COLOR_MAP[tag] = "#FFFFFF"
                self.tree.tag_configure(tag, background=COLOR_MAP[tag])

            # Hauteur dynamique
            row_height = 25 #+ (max_lines - 1) * 18
            self.tree.item(item_id)
            self.tree.configure(style="Custom.Treeview")

            style = ttk.Style()
            style.configure("Custom.Treeview", rowheight=row_height)

        # Mise à jour compteur
        self.counter_label.configure(
            text=f"{len(self.filtered_data)} élément(s)"
        )

    # =========================
    # Open Item
    # =========================
    def on_double_click(self, event):

        selected = self.tree.selection()
        if not selected:
            return

        item_id = selected[0]
        values = self.tree.item(item_id)["values"]
        tags = self.tree.item(item_id)["tags"]

        # Couleur associée à l'acte
        bg_color = None
        if tags:
            acte = tags[0]
            bg_color = COLOR_MAP.get(acte, None)

        self.open_detail_window(values, bg_color)
    
    # =========================
    # Detailed Window
    # =========================
    def open_detail_window(self, values, bg_color):

        detail = ctk.CTkToplevel(self)
        detail.title("Détail de l'événement")
        detail.geometry("600x500")

        # Bloquant (modal)
        detail.grab_set()
        detail.focus()
        detail.transient(self)

        if bg_color:
            detail.configure(fg_color=bg_color)

        # Frame principale
        frame = ctk.CTkFrame(detail, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Zone texte scrollable
        textbox = ctk.CTkTextbox(frame, wrap="word")
        textbox.pack(fill="both", expand=True)

        # Construire le texte avec le nom des colonnes
        columns = self.tree["columns"]  # récupère toutes les colonnes
        content_lines = []
        for col, val in zip(columns, values):
            content_lines.append(f"{col}: {val}")

        content = "\n\n".join(content_lines)
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

        # Bouton fermer
        close_button = ctk.CTkButton(
            frame,
            text="Fermer",
            command=detail.destroy
        )
        close_button.pack(pady=15)

        # Attente fermeture (vraiment bloquant)
        self.wait_window(detail)


    # =========================
    # Refresh
    # =========================
    def refresh(self):
        print(f"Refreshing data at {datetime.now().strftime('%H:%M:%S')}...")
        self.show_loading()
        self.after(100, self.load_data)

    # =========================
    # Toggle Envoi Aujourd'hui
    # =========================
    def toggle_today_tx_filter(self):

        self.today_tx_filter_active = not self.today_tx_filter_active

        if self.today_tx_filter_active:
            self.today_tx_button.configure(fg_color="green")
        else:
            self.today_tx_button.configure(
                fg_color=self.default_today_color)

        self.apply_filters()

    # =========================
    # Toggle Réception Aujourd'hui
    # =========================
    def toggle_today_rx_filter(self):

        self.today_rx_filter_active = not self.today_rx_filter_active

        if self.today_rx_filter_active:
            self.today_rx_button.configure(fg_color="green")
        else:
            self.today_rx_button.configure(
                fg_color=self.default_today_color)

        self.apply_filters()

    # =========================
    # Menu multi-actes
    # =========================
    def open_acte_menu(self):

        self.acte_window = tk.Toplevel(self)
        self.acte_window.title("Sélection des actes")
        self.acte_window.geometry("350x450")
        self.acte_window.grab_set()

        canvas = tk.Canvas(self.acte_window)
        scrollbar = ttk.Scrollbar(
            self.acte_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0),
                             window=scrollable_frame,
                             anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.temp_acte_vars = {}

        for acte in self.acte_values:
            var = tk.BooleanVar(
                value=acte in self.selected_actes)
            self.temp_acte_vars[acte] = var

            cb = tk.Checkbutton(
                scrollable_frame,
                text=acte,
                variable=var
            )
            cb.pack(anchor="w")

        select_button_frame = tk.Frame(self.acte_window)
        select_button_frame.pack(fill="x", pady=10)
    
        tk.Button(select_button_frame, text="Tout sélectionner",
                  command=self.select_all_actes).pack(side="left", padx=5)

        tk.Button(select_button_frame, text="Tout désélectionner",
                  command=self.deselect_all_actes).pack(side="left", padx=5)


        button_frame = tk.Frame(self.acte_window)
        button_frame.pack(fill="x", pady=10)
    
        tk.Button(button_frame, text="OK",
                  command=self.validate_actes).pack(side="left", padx=5)
        tk.Button(button_frame, text="Annuler",
                  command=self.acte_window.destroy).pack(side="left", padx=5)

    def select_all_actes(self):
        for var in self.temp_acte_vars.values():
            var.set(True)

    def deselect_all_actes(self):
        for var in self.temp_acte_vars.values():
            var.set(False)

    def validate_actes(self):

        self.selected_actes = {
            acte for acte, var in self.temp_acte_vars.items()
            if var.get()
        }

        if self.selected_actes:
            self.acte_button.configure(
                text=f"{len(self.selected_actes)} acte(s)"
            )
        else:
            self.acte_button.configure(text="Choisir actes")

        self.acte_window.destroy()
        self.apply_filters()

    # =========================
    # Application filtres
    # =========================
    def apply_filters(self, _=None):

        proth_value = self.proth_filter.get()
        self.filtered_data = []

        today_str = date.today().isoformat()

        for row in self.full_data:

            if proth_value != "Tous" and \
               row["Prothésiste"] != proth_value:
                continue

            if self.selected_actes and \
               row["Acte prothésiste"] not in self.selected_actes:
                continue

            if self.today_tx_filter_active:
                my_date = datetime.strptime(row["Date d'envoi au labo"], "%d/%m/%Y").date()
                if my_date.isoformat() != today_str:
                    continue

            if self.today_rx_filter_active:
                my_date = datetime.strptime(row["Date de réception"], "%d/%m/%Y").date()
                if my_date.isoformat() != today_str:
                    continue

            self.filtered_data.append(row)

        self.apply_sort()
        self.populate_table()

    # =========================
    # Tri colonnes
    # =========================
    def sort_column(self, col):

        # Si on reclique la même colonne → on inverse
        if self.current_sort_column == col:
            self.current_sort_reverse = not self.current_sort_reverse
        else:
            # Nouvelle colonne → tri croissant par défaut
            self.current_sort_column = col
            self.current_sort_reverse = False

        self.apply_sort()
        self.populate_table()

    def apply_sort(self):

        if not self.current_sort_column:
            return

        col = self.current_sort_column

        def try_parse(value):

            if col in ["Date d'envoi au labo", "Date de réception"]:
                try:
                    return datetime.strptime(value, "%d/%m/%Y %H:%M")
                except:
                    try:
                        return datetime.strptime(value, "%d/%m/%Y")
                    except:
                        return datetime.min

            try:
                return float(value)
            except:
                pass

            return str(value).lower()

        self.filtered_data.sort(
            key=lambda x: try_parse(x[col]),
            reverse=self.current_sort_reverse
        )

def main():
    app = App()
    app.mainloop()

# =========================
# Lancement
# =========================
if __name__ == "__main__":
    main()
