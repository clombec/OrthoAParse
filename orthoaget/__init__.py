# orthoaget/__init__.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# PROJECT_ROOT always points to the root of the OrthoAGet project, regardless of where this file is imported from. This allows us to use relative paths from the project root in our code.