"""
OrthoALogger.py

Centralized logging setup for OrthoAParse.
- Logs to console and to logs/OrthoAProth.log, in a logs/ subfolder next to the .exe
- On startup, if OrthoAProth.log exceeds 500 KB, it is renamed with the current
  date/time and a new empty log file is created
- Every log line includes date and time prefix (handled by the formatter)
- Call setup_logger() once at app startup, then use logging.getLogger() anywhere
"""

import logging
import os
import sys
from datetime import datetime

LOG_FILE = "OrthoAProth.log"
LOG_DIR = "logs"
MAX_LOG_SIZE_BYTES = 500 * 1024  # 500 KB


def get_log_dir():
    """
    Return the logs/ directory path, located next to the .exe (or next to the
    script when running from source). Creates the directory if it doesn't exist.
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller .exe — use the directory containing the .exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # Running from source — use the project root (two levels up from OrthoABase/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    log_dir = os.path.join(base_dir, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def rotate_if_needed(log_path):
    """
    If the log file exceeds MAX_LOG_SIZE_BYTES, rename it with the current
    date/time suffix so it is archived, and let a new empty file be created.
    """
    if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_SIZE_BYTES:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_name = f"OrthoAProth_{timestamp}.log"
        archived_path = os.path.join(os.path.dirname(log_path), archived_name)
        os.rename(log_path, archived_path)
        print(f"[OrthoALogger] Log file exceeded 500 KB — archived as {archived_name}")


def setup_logger():
    """
    Configure the root logger with:
    - A FileHandler writing to logs/OrthoAProth.log
    - A StreamHandler writing to the console
    Both use the same formatter: YYYY-MM-DD HH:MM:SS | LEVEL | message
    A startup separator line is written to mark each new session.
    Call this once at the entry point of each app.
    """
    log_dir = get_log_dir()
    log_path = os.path.join(log_dir, LOG_FILE)

    rotate_if_needed(log_path)

    # Formatter: date/time prefix on every line
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler — appends to current log file
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Root logger setup
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Write a startup separator so sessions are easy to tell apart in the log file
    logger.info("=" * 60)
    logger.info("Application started")
    logger.info("=" * 60)

    return logger
