import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "data" / "goldsea.db"))
APP_NAME = "GoldSea AI Chatbot"
APP_VERSION = "1.0.0"

# Target user configuration
TARGET_USER_NAME = "Gokul"
