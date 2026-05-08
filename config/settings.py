import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Lee secrets de Streamlit Cloud o variables de entorno."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, default)


# Rutas base
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INPUTS_DIR = DATA_DIR / "inputs"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
OUTPUTS_DIR = DATA_DIR / "outputs"
RULES_DIR = DATA_DIR / "rules"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"

# Anthropic
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-5"

# Google Drive
GOOGLE_DRIVE_FOLDER_ID = _get_secret("GOOGLE_DRIVE_FOLDER_ID")

# Entorno
ENVIRONMENT = _get_secret("ENVIRONMENT", "development")

# Crear carpetas necesarias al arrancar
for _folder in [INPUTS_DIR, INTERMEDIATE_DIR, OUTPUTS_DIR, RULES_DIR]:
    _folder.mkdir(parents=True, exist_ok=True)
