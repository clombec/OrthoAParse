"""
OrthoAdl.py

Access the OrthoAdvance web application, log in as a specific user
then download pages in CSV format or in other formats.
OrthoAdvance url and credentials are taken from an external config file.

This script uses Selenium to automate the web browser interactions.
"""

from socket import timeout
from symtable import Class
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging
import os
import time
import shutil
import yaml
from datetime import datetime


class OrthoAConnectionError(Exception):
    """Raised when OrthoAdvance is unreachable or login fails."""
    pass


class OrthoADownloadError(Exception):
    """Raised when a download or page fetch fails."""
    pass


class OrthoAdl():
    def __init__(self, download_dir, no_dl=False):
        self.no_dl = no_dl
        self.download_dir = download_dir
        # Load YAML configuration file
        with open("OrthoABase/config.yaml", "r") as file:
            config = yaml.safe_load(file)
        # Get the connection values
        self.OrthoAUrlBase = f"https://{config['connexion']['url']}.orthoadvance.com"
        self.OrthoAlogin = config['connexion']['login']
        self.OrthoAPwd = config['connexion']['pwd']

        if not self.no_dl:
            self.connect(download_dir)

    def wait_login_flow(self, timeout=10):
        def check(d):
            try:
                el = d.find_element(By.ID, "users-0")
                if el.is_displayed() and el.is_enabled():
                    return ("user_page", el)
            except:
                pass

            if d.find_elements(By.ID, "password"):
                return ("password_page", None)

            return False

        return WebDriverWait(self.driver, timeout).until(check)

    def connect(self, download_dir):
        logging.info("Connecting to OrthoAdvance...")
        try:
            # Configure Chrome options for downloads
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
            try:
                self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            except Exception:
                # ChromeDriver cache may be stale (e.g. after a Chrome update) — force re-download and retry once
                logging.warning("ChromeDriver failed to start — clearing cache and retrying...")
                ChromeDriverManager().install.__func__  # flush not needed, just reinstall with cache_valid=0
                self.driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager(cache_valid_range=0).install()),
                    options=chrome_options
                )

            logging.info("Chrome driver initialized.")
            # 1. Access the user selection page
            connect_url = f"{self.OrthoAUrlBase}/#!/login/connect"
            self.driver.get(connect_url)
            logging.info(f"Login page loaded. URL: {connect_url}")

            result, element = self.wait_login_flow(10)

            if result == "user_page" and element:
                element.click()
                # 3. Wait for the password page
                logging.info("Waiting for password page...")
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "password"))
                    )

            elif result == "password_page":
                pass

            # 4.1 fill in the email field
            email_field = self.driver.find_element(By.ID, "email")
            email_field.clear()
            email_field.send_keys(self.OrthoAlogin)
            # 4.2 fill in the password field
            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.OrthoAPwd)

            logging.info("Credentials entered.")
            # 5. Click on the "Me connecter" button
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "btn-form-submit"))
            )
            login_button.click()

            logging.info("Login submitted.")
            # 6. Wait for main page after login
            WebDriverWait(self.driver, 10).until(
                lambda d: (
#                d.execute_script("return document.readyState") == "complete" and
                    d.current_url != connect_url
                )
            )
            logging.info("Login successful.")

        except Exception as e:
            raise OrthoAConnectionError(
                f"Impossible de se connecter à OrthoAdvance : {e}"
            ) from e

    def downloadCsv(self, pageUrl):
        logging.info("Starting CSV download...")
        # Access the page with the CSV export button
        driver = self.driver
        driver.get(f"{self.OrthoAUrlBase}/{pageUrl}")

        try:
            logging.info(f"Accessing page: {self.OrthoAUrlBase}/{pageUrl}")
            # 8. Click on the CSV export button
            wait = WebDriverWait(driver, 15)

            export_button = wait.until(
                lambda d: (
                    d.find_element(By.CSS_SELECTOR, 'button[name="action"][value="export_as_csv"]')
                    if d.find_elements(By.CSS_SELECTOR, 'button[name="action"][value="export_as_csv"]')
                    else d.find_element(By.CSS_SELECTOR, 'a.btn.btn-link[href*="csv"]')
                    if d.find_elements(By.CSS_SELECTOR, 'a.btn.btn-link[href*="csv"]')
                    else d.find_element(By.XPATH, "//button[normalize-space()='Exporter au format CSV']")
                )
            )

            logging.info("Export button found. Clicking to start download...")
            export_button.click()

            # 9. Wait for the download to start
            logging.info("Waiting for download to complete...")

            downloaded_file = self.wait_for_download((".csv"))

            # 10. Verify that the CSV file has been downloaded
            logging.info(f"Download complete. File saved to: {downloaded_file}")

            return downloaded_file

        except TimeoutError:
            raise
        except Exception as e:
            raise OrthoADownloadError(
                f"Échec du téléchargement CSV ({pageUrl}) : {e}"
            ) from e

    def wait_for_download(self, file_extension, timeout=60):
        """
        Wait until a file is completely downloaded in download_dir.
        Returns the path of downloaded file.
        """

        start_time = time.time()

        while True:
            files = os.listdir(self.download_dir)

            # Ignore les fichiers temporaires Chrome (.crdownload)
            completed_files = [
                f for f in files
                if f.endswith(file_extension)
            ]

            if completed_files:
                logging.info(f"File downloaded: {completed_files[0]}")
                return os.path.join(self.download_dir, completed_files[0])

            if time.time() - start_time > timeout:
                logging.error("Download timeout reached.")
                raise TimeoutError("Téléchargement non détecté dans le délai imparti")

            time.sleep(0.5)

    def downloadPageHtml(self, pageUrl, filename="page_content.html"):
        # Access the page and download text content
        driver = self.driver
        logging.info(f"Accessing page: {self.OrthoAUrlBase}/{pageUrl}")
        try:
            driver.get(f"{self.OrthoAUrlBase}/{pageUrl}")

            # Wait for the page to load
            time.sleep(2)

            # Retrieve the page HTML
            html = driver.page_source

            # Save to file
            filename = os.path.join(self.download_dir, filename)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)

        except Exception as e:
            raise OrthoADownloadError(
                f"Échec du téléchargement HTML ({pageUrl}) : {e}"
            ) from e

    def downloadPageText(self, pageUrl, filename="page_content.txt"):
        # Access the page and download text content
        driver = self.driver
        logging.info(f"Accessing page: {self.OrthoAUrlBase}/{pageUrl}")
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

            logging.info(f"Page text saved to {filename}")

        except Exception as e:
            raise OrthoADownloadError(
                f"Échec du téléchargement texte ({pageUrl}) : {e}"
            ) from e

    def end(self):
        if not self.no_dl:
            self.driver.quit()


"""
local run function for testing purposes. Not intended for production use.
"""
def run():
    # Setup the download directory and clear existing files if any
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
                logging.error(f"Could not remove {path}: {e}")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    orthoAdl = OrthoAdl(download_dir)
    orthoAdl.downloadPageHtml("ang/#!/planning/preparation/jtypes/list/active")
#    orthoAdl.downloadPageText("planning/calendar/;events_view?jt=/planning/jt/journees/5&mode=jt&cabinet=/config-application/cabinets/0&praticien=", "calendar_events.txt")
#    orthoAdl.downloadPageText("planning/jt/journees/5/;view?json=1")
    orthoAdl.end()


if __name__ == "__main__":
    run()