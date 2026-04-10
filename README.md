# OrthoAParse

A data extraction and processing tool for **OrthoAdvance** (orthodontic practice management software), using Selenium/Chrome automation.

## Features

- **Data extraction**: automatic login to OrthoAdvance and retrieval of data (income records, prosthetics acts, patients) in CSV, JSON, or HTML format.
- **Discord notifications**: automatic posting of daily income totals to a Discord channel via webhook.
- **Income web interface** (`WebRecettes`): single-button UI to manually trigger extraction and Discord notification (Flask, port 5001).
- **Prosthetics web interface** (`OrthoAProthData`): filterable and sortable table of prosthetics acts with configurable color coding (Flask, port 5002).
- **Scheduled mode**: automatic hourly execution between 8 AM and 7 PM.

## Requirements

- Python 3.11+
- Google Chrome installed (used by Selenium WebDriver)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-account>/OrthoAParse.git
cd OrthoAParse
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure OrthoAdvance access

Run the interactive setup script:

```bash
python -m OrthoABase.config_setup
```

You will be prompted for:
- **URL prefix** for OrthoAdvance (e.g. `myoffice-app`)
- **Login** (email address)
- **Password** — stored securely in the system keyring (Keychain on macOS, Credential Manager on Windows, SecretService on Linux)
- **Discord webhook URL** (optional) — for automatic income notifications

Credentials are stored via `keyring`. URL and webhook are saved in `OrthoABase/config.yaml`.

To display the current configuration:

```bash
python -m OrthoABase.config_setup show
```

To remove credentials from the keyring:

```bash
python -m OrthoABase.config_setup clear
```

## Usage

### Income extraction (with Discord notification)

```bash
# One-shot run
python mainRecettes.py

# Scheduled mode (every hour, 8 AM–7 PM)
# Set SCHEDULED_RUN = True in mainRecettes.py, then:
python mainRecettes.py
```

### Programmatic usage

```python
from orthoaget.session import OrthoASession

with OrthoASession() as session:
    data = get_xxx_records()
    print(data)
```

## Project structure

```
OrthoAParse/
├── OrthoABase/          # Connection, parsing, configuration
│   ├── config_setup.py  # Interactive setup script
│   ├── config.yaml      # URL and webhook (generated at setup)
│   └── urls.yaml        # Endpoint definitions
├── OrthoARecettes/      # Income logic and Discord dispatch
├── OrthoAProthData/     # Prosthetics web interface
├── WebRecettes/         # Income web interface
├── orthoaget/           # Session facade and logger
├── mainRecettes.py      # Income entry point
├── mainProth.py         # Prosthetics interface entry point
├── mainWeb.py           # Income web interface entry point
└── requirements.txt
```

## Key dependencies

| Package | Purpose |
|---|---|
| `selenium` + `webdriver_manager` | Chrome automation |
| `beautifulsoup4` | HTML parsing |
| `pandas` | CSV data processing |
| `flask` | Web interfaces |
| `keyring` | Secure credential storage |
| `pyyaml` | Configuration files |
| `customtkinter` / `pillow` | GUI (optional) |
