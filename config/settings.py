import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-5"

# Google Drive
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# Entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")