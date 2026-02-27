"""
OrthoAdl.py

Access the OrthoAdvance web application, log in as a specific user
then download pages in CSV format or in other formats.
OrthoAdvance url and credentials are taken from an external config file.

This script uses Selenium to automate the web browser interactions.
"""

from symtable import Class
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import time
import shutil
import yaml

class OrthoAdl():
    def __init__(self, download_dir, no_dl=False):
        self.no_dl = no_dl
        self.download_dir = download_dir
        # Charge YAML configuration file
        with open("OrthoABase/config.yaml", "r") as file:
            config = yaml.safe_load(file)
        # Get the connection values
        self.OrthoAUrlBase = f"https://{config['connexion']['url']}.orthoadvance.com"
        self.OrthoAlogin = config['connexion']['login']
        self.OrthoAPwd = config['connexion']['pwd']

        if not self.no_dl:
            self.connect(download_dir)

    def connect(self, download_dir):
        # Configurer Chrome options for downloads
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Hidden mode. Comment to show the browser
        chrome_options.add_argument("--disable-gpu")  # Needed for some Chrome versions
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # Initialize Chrome driver
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

        # 1. Access the user selection page
        connect_url = f"{self.OrthoAUrlBase}/#!/login/connect"
        self.driver.get(connect_url)        

        try:
            # 2. Select user 0
            user_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "users-0"))
            )
            user_button.click()
        except Exception as e:
            print(f"No init page : {e}")

        # 3. Wait for the password page
        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.ID, "password"))
        )

        # 4.1 fill in the email field
        email_field = self.driver.find_element(By.ID, "email")
        email_field.clear()
        email_field.send_keys(self.OrthoAlogin)
        # 4.2 fill in the password field
        password_field = self.driver.find_element(By.ID, "password")
        password_field.send_keys(self.OrthoAPwd)

        # 5. Click on the "Me connecter" button
        login_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "btn-form-submit"))
        )
        login_button.click()

        # 6. Attendre la page principale après la connexion
        time.sleep(5)  # Attendre 5 secondes

    def downloadCsv(self, pageUrl):
        # Access the page with the CSV export button
        driver = self.driver
        driver.get(f"{self.OrthoAUrlBase}/{pageUrl}")

        try:
            # 8. Click on the CSV export button
            wait = WebDriverWait(driver, 15)

            export_button = wait.until(
                lambda d: (
                    d.find_element(By.CSS_SELECTOR, 'button[name="action"][value="export_as_csv"]')
                    if d.find_elements(By.CSS_SELECTOR, 'button[name="action"][value="export_as_csv"]')
                    else d.find_element(By.XPATH, "//button[normalize-space()='Exporter au format CSV']")
                )
            )

            export_button.click()

            # 9. Wait for the download to start
            print("Downloading...")

            downloaded_file = self.wait_for_download()

            # 10. Verify that the CSV file has been downloaded
            print("Download complete. Check the 'downloads' folder")

            return downloaded_file

        except Exception as e:
            print(f"An error occurred: {e}")

    def wait_for_download(self, timeout=30):
        """
        Attend qu'un fichier soit complètement téléchargé dans download_dir.
        Retourne le chemin du fichier téléchargé.
        """

        start_time = time.time()

        while True:
            files = os.listdir(self.download_dir)

            # Ignore les fichiers temporaires Chrome (.crdownload)
            completed_files = [
                f for f in files
                if not f.endswith(".crdownload")
            ]

            if completed_files:
                return os.path.join(self.download_dir, completed_files[0])

            if time.time() - start_time > timeout:
                raise TimeoutError("Téléchargement non détecté")

            time.sleep(0.5)

    def downloadPageHtml(self, pageUrl, filename="page_content.html"):
        # Access the page and download text content
        driver = self.driver
        print(f"Accessing page: {self.OrthoAUrlBase}/{pageUrl}")
        driver.get(f"{self.OrthoAUrlBase}/{pageUrl}")

        # Wait for the page to charge
        time.sleep(2)

        # Récupérer le HTML de la page
        html = driver.page_source

        # Save to file
        filename = os.path.join(self.download_dir, filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)        


    def downloadPageText(self, pageUrl, filename="page_content.txt"):
        # Access the page and download text content
        driver = self.driver
        print(f"Accessing page: {self.OrthoAUrlBase}/{pageUrl}")
        driver.get(f"{self.OrthoAUrlBase}/{pageUrl}")
        
        try:
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Extract page text
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Save to file
            filename = os.path.join(self.download_dir, filename)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(page_text)
            
            print(f"Page text saved to {filename}")
            
        except Exception as e:
            print(f"An error occurred: {e}")

    def end(self):
        if not self.no_dl:
            self.driver.quit()

def run():
    # Configurer le dossier de téléchargement
    download_dir = os.path.abspath("downloads")
    if os.path.exists(download_dir):
        for entry in os.listdir(download_dir):
            path = os.path.join(download_dir, entry)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as e:
                print(f"Could not remove {path}: {e}")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    orthoAdl = OrthoAdl(download_dir)
    orthoAdl.downloadPageHtml("ang/#!/planning/preparation/jtypes/list/active")
#    orthoAdl.downloadPageText("planning/calendar/;events_view?jt=/planning/jt/journees/5&mode=jt&cabinet=/config-application/cabinets/0&praticien=", "calendar_events.txt")
#    orthoAdl.downloadPageText("planning/jt/journees/5/;view?json=1")
    orthoAdl.end()



if __name__ == "__main__":
    run()