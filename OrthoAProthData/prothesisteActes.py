import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import yaml
import logging
from datetime import datetime, date
import OrthoABase.OrthoAdl as OrthoAdl
from orthoaget.session import OrthoASession
from orthoaget.logger import setup_logger
from tkinter import colorchooser
import platform

from orthoaget import PROJECT_ROOT


# =========================
# Application
# =========================
class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Actes Prothésiste")
        self.geometry("900x500")
        self.after(0, lambda: self.wm_iconbitmap("OrthoAProthData/OrthoAProth.ico"))
        self.mark_done_str = "✓ Marquer réalisé "
        self.set_done = None  # callable(acte_urls) captured from session

        self.full_data = []
        self.filtered_data = []

        # Color and column maps — loaded from Configuration.yaml in load_data()
        self.color_map = {}
        self.column_map = {}

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

        # Disable table content while loading
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Loading overlay
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

    def show_error(self, message):
        """Replace the loading overlay with a visible error message + retry button."""
        self.hide_loading()

        self.error_frame = ctk.CTkFrame(self)
        self.error_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self.error_frame,
            text="⚠️ Erreur de connexion",
            font=("Arial", 18, "bold"),
            text_color="red"
        ).pack(padx=40, pady=(30, 10))

        ctk.CTkLabel(
            self.error_frame,
            text=message,
            font=("Arial", 13),
            wraplength=420,
            justify="center"
        ).pack(padx=40, pady=(0, 20))

        ctk.CTkButton(
            self.error_frame,
            text="Réessayer",
            command=self.retry_load,
            width=140
        ).pack(pady=(0, 30))

    def hide_error(self):
        if hasattr(self, "error_frame"):
            self.error_frame.destroy()

    def retry_load(self):
        self.hide_error()
        self.show_loading()
        self.after(100, self.load_data)

    def load_data(self):

        with open(f"{PROJECT_ROOT}/OrthoAProthData/Configuration.yaml", "r", encoding="utf-8") as f:
            yamlconfig = yaml.safe_load(f)
            self.color_map = yamlconfig.get("colors", {})
            self.column_map = yamlconfig.get("columns", {})

        try:
            with OrthoASession() as session:
                self.full_data = session.get_proth_records()
                self.set_done = session.make_proth_set_done()
        except OrthoAdl.OrthoAConnectionError as e:
            logging.error(f"Erreur de connexion : {e}")
            self.show_error(str(e))
            return
        except OrthoAdl.OrthoADownloadError as e:
            logging.error(f"Erreur de téléchargement : {e}")
            self.show_error(str(e))
            return
        except Exception as e:
            logging.error(f"Erreur inattendue : {e}")
            self.show_error(f"Erreur inattendue : {e}")
            return

        for line in self.full_data:
            line["url"] = f"{self.mark_done_str}{line['url']}"

        logging.info(f"Data loaded. {len(self.full_data)} records found.")

        self.setup_columns()
        self.update_filters()

        self.apply_filters()

        self.hide_loading()

        logging.info(f"Data processing complete. Table populated with {len(self.filtered_data)} records.")

    # =========================
    # Filters
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

        # Activate/deactivate the "sent today" filter button UI
        self.today_tx_button = ctk.CTkButton(
            frame,
            text="Envoi Aujourd'hui",
            command=self.toggle_today_tx_filter,
            width=150
        )
        self.today_tx_button.pack(side="left", padx=10)
        self.default_today_color = self.today_tx_button.cget("fg_color")

        # Activate/deactivate the "received today" filter button UI
        self.today_rx_button = ctk.CTkButton(
            frame,
            text="Reception Aujourd'hui",
            command=self.toggle_today_rx_filter,
            width=150
        )
        self.today_rx_button.pack(side="left", padx=10)

        # Refresh button container label
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

        # Update prosthetist dropdown values
        self.proth_filter.configure(
            values=["Tous"] + proth_values
        )

        # Update acts list cache
        self.acte_values = acte_values

    # =========================
    # Color manager menu
    # =========================
    def open_color_manager(self):

        self.color_window = tk.Toplevel(self)
        self.color_window.title("Gestion des couleurs des actes")
        self.color_window.geometry("450x550")
        self.color_window.grab_set()

        # ===== MAIN FRAME =====
        main_frame = tk.Frame(self.color_window)
        main_frame.pack(fill="both", expand=True)

        # ===== SCROLLABLE CANVAS =====
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

        # ===== MOUSE WHEEL SCROLL =====
        def _on_mousewheel(event):
            """Normalize mouse wheel events across platforms."""
            system = platform.system()

            if system == "Windows":
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            elif system == "Darwin":
                canvas.yview_scroll(int(-1 * event.delta / 2), "units")

            else:  # Linux scroll bindings
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")

        # Windows & macOS scroll bindings
        canvas.bind("<MouseWheel>", _on_mousewheel)

        # Linux scroll bindings
        canvas.bind("<Button-4>", _on_mousewheel)
        canvas.bind("<Button-5>", _on_mousewheel)

        # ===== CONTENT =====
        self.temp_colors = self.color_map.copy()
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

        # ===== BOTTOM FIXED BUTTONS =====
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

        if color_code[1]:  # if not cancelled
            self.temp_colors[acte] = color_code[1]
            self.color_squares[acte].configure(bg=color_code[1])

    def save_colors(self):

        self.color_map = self.temp_colors.copy()
        #self.column_map = self.temp_columns.copy()

        with open(f"{PROJECT_ROOT}/OrthoAProthData/configuration.yaml", "w", encoding="utf-8") as f:
            config = {
                "colors": self.color_map,
                "columns": self.column_map
            }
            yaml.dump(config, f, allow_unicode=True)

        self.color_window.destroy()

        # Reload table colors after save and close color editor
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
            acte_url = self.tree.item(item)["values"][col_index].replace(self.mark_done_str, "")
            if acte_url:
                self.markActeAsDone(acte_url)

    def setup_columns(self):

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
            ww = self.column_map.get(col, {}).get("width", 170)
            self.tree.column(col, width=ww, anchor="center")

    # =========================
    # Table populate
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

            # Apply color per act taxon
            if tag in self.color_map:
                self.tree.tag_configure(tag, background=self.color_map[tag])
            else:
                self.color_map[tag] = "#FFFFFF"
                self.tree.tag_configure(tag, background=self.color_map[tag])

            # Dynamic row height based on comment lines
            row_height = 25 #+ (max_lines - 1) * 18
            self.tree.item(item_id)
            self.tree.configure(style="Custom.Treeview")

            style = ttk.Style()
            style.configure("Custom.Treeview", rowheight=row_height)

        # Update row counter label
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

        # Fetch background color linked to act
        bg_color = None
        if tags:
            acte = tags[0]
            bg_color = self.color_map.get(acte, None)

        self.open_detail_window(values, bg_color)

    # =========================
    # Detailed Window
    # =========================
    def open_detail_window(self, values, bg_color):

        detail = ctk.CTkToplevel(self)
        detail.title("Détail de l'événement")
        detail.geometry("600x500")

        # Block input to parent window (modal)
        detail.grab_set()
        detail.focus()
        detail.transient(self)

        if bg_color:
            detail.configure(fg_color=bg_color)

        # Main frame for detail view
        frame = ctk.CTkFrame(detail, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Scrollable text box for details
        textbox = ctk.CTkTextbox(frame, wrap="word")
        textbox.pack(fill="both", expand=True)

        # Build display text with column names
        columns = self.tree["columns"]  # retrieve all column names
        content_lines = []
        for col, val in zip(columns, values):
            content_lines.append(f"{col}: {val}")

        content = "\n\n".join(content_lines)
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

        # Close button
        close_button = ctk.CTkButton(
            frame,
            text="Fermer",
            command=detail.destroy
        )
        close_button.pack(pady=15)

        # Wait until details window is closed
        self.wait_window(detail)

    # =========================
    # Refresh controls
    # =========================
    def refresh(self):
        logging.info("Refreshing data...")
        self.show_loading()
        self.after(100, self.load_data)

    # =========================
    # Toggle "sent today" filter
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
    # Toggle "received today" filter
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
    # Multi-act selection menu
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
    # Apply filters to data set
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
                # Only include rows sent to lab today
                my_date = datetime.strptime(row["Date d'envoi au labo"], "%d/%m/%Y").date()
                if my_date.isoformat() != today_str:
                    continue

            if self.today_rx_filter_active:
                # Only include rows received today
                my_date = datetime.strptime(row["Date de réception"], "%d/%m/%Y").date()
                if my_date.isoformat() != today_str:
                    continue

            self.filtered_data.append(row)

        self.apply_sort()
        self.populate_table()

    # =========================
    # Column sorting
    # =========================
    def sort_column(self, col):

        # If the same column is clicked again, reverse sorting order
        if self.current_sort_column == col:
            self.current_sort_reverse = not self.current_sort_reverse
        else:
            # New column clicked -> default to ascending sort
            self.current_sort_column = col
            self.current_sort_reverse = False

        self.apply_sort()
        self.populate_table()

    def apply_sort(self):

        if not self.current_sort_column:
            return

        col = self.current_sort_column

        def try_parse(value):
            """Convert values for stable sorting by date/numeric/text."""

            if col in ["Date d'envoi au labo", "Date de réception"]:
                # Skip empty values — no format error to log here
                if not value:
                    return datetime.min
                try:
                    return datetime.strptime(value, "%d/%m/%Y %H:%M")
                except ValueError:
                    try:
                        return datetime.strptime(value, "%d/%m/%Y")
                    except ValueError:
                        logging.warning(
                            f"Unrecognised date format in column '{col}': '{value}' — defaulting to min date"
                        )
                        return datetime.min

            try:
                return float(value)
            except (ValueError, TypeError):
                pass

            return str(value).lower()

        self.filtered_data.sort(
            key=lambda x: try_parse(x[col]),
            reverse=self.current_sort_reverse
        )

    def markActeAsDone(self, acte_url: str) -> None:
        """Mark a single act as done and show visual feedback."""
        if not self.set_done:
            tk.messagebox.showerror("Erreur", "Session expirée, veuillez rafraîchir.")
            return
        try:
            self.set_done([acte_url])
            logging.info(f"[markActeAsDone] OK: {acte_url}")
            tk.messagebox.showinfo("Succès", "Acte marqué comme réalisé.")
        except Exception as e:
            logging.error(f"[markActeAsDone] Erreur: {e}")
            tk.messagebox.showerror("Erreur", f"Impossible de marquer l'acte :\n{e}")


def main():
    setup_logger()

    # Set AppUserModelID so Windows taskbar shows the correct icon
    try:
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("OrthoAProth")
    except Exception:
        pass  # non-Windows — ignore silently

    app = App()
    app.mainloop()

# =========================
# Launch
# =========================
if __name__ == "__main__":
    main()