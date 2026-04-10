"""
setup_console.py

Interactive console module to configure OrthoAGet:
  - OrthoAdvance URL prefix  → saved in config.yaml
  - Discord webhook URL      → saved in config.yaml
  - Login (email)            → saved in system keyring (Windows Credential Manager / macOS Keychain / SecretService)
  - Password                 → saved in system keyring (Windows Credential Manager / macOS Keychain / SecretService)
"""

import os
import getpass
import yaml
import keyring
from orthoaget import PROJECT_ROOT

KEYRING_SERVICE = "OrthoAGet"
CONFIG_PATH = f"{PROJECT_ROOT}/OrthoABase/config.yaml"


def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _prompt(label, current=None, secret=False):
    hint = f" [{current}]" if current and not secret else (" [set]" if current and secret else "")
    prompt_str = f"{label}{hint}: "
    if secret:
        value = getpass.getpass(prompt_str)
    else:
        value = input(prompt_str).strip()
    return value if value else current


def setup():
    print("\n=== OrthoAGet - Configuration ===")

    config = _load_config()
    current_url     = config.get("connexion", {}).get("url", "")
    current_webhook = config.get("discord", {}).get("webhook", "")
    current_login   = keyring.get_password(KEYRING_SERVICE, "login")
    current_pwd     = keyring.get_password(KEYRING_SERVICE, "password")

    print("\n-- OrthoAdvance connection --")
    url     = _prompt("URL prefix (e.g. 'myoffice-app')", current_url)
    login   = _prompt("Login (email)", current_login)
    pwd     = _prompt("Password", current_pwd, secret=True)

    print("\n-- Discord (optional) --")
    webhook = _prompt("Webhook URL (leave blank to skip)", current_webhook)

    # Save config.yaml
    config["connexion"] = {"url": url}
    config["discord"]   = {"webhook": webhook or ""}
    _save_config(config)
    print(f"\nConfig saved: {CONFIG_PATH}")

    # Save credentials to keyring
    if login:
        keyring.set_password(KEYRING_SERVICE, "login", login)
    if pwd:
        keyring.set_password(KEYRING_SERVICE, "password", pwd)
    print("Credentials saved to system keyring.")

    print("\n=== Configuration complete ===\n")


def show():
    """Display current configuration (password masked)."""
    print("\n=== OrthoAGet - Current configuration ===")

    config = _load_config()
    url     = config.get("connexion", {}).get("url", "(not set)")
    webhook = config.get("discord", {}).get("webhook", "(not set)")
    login   = keyring.get_password(KEYRING_SERVICE, "login") or "(not set)"
    pwd     = keyring.get_password(KEYRING_SERVICE, "password")
    pwd_display = "***" if pwd else "(not set)"

    print(f"  URL prefix : {url}")
    print(f"  Login      : {login}")
    print(f"  Password   : {pwd_display}")
    print(f"  Webhook    : {webhook or '(not set)'}")
    print()


def clear_credentials():
    """Remove credentials from keyring."""
    for key in ("login", "password"):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass
    print("Credentials removed from keyring.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if cmd == "show":
        show()
    elif cmd == "clear":
        clear_credentials()
    else:
        setup()
