import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Safely load local .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

def get_port() -> int:
    raw = os.environ.get("PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return 8080

PORT = get_port()
HOST = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower() or "development"

# Base URL for public links (in production: live Render URL)
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
if not APP_BASE_URL:
    APP_BASE_URL = f"http://localhost:{PORT}"

# Secret Key (32+ bytes for signing session cookies and CSRF tokens)
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY and ENVIRONMENT != "production":
    SECRET_KEY = "94b3a81eaa387e2e9da652e92b1b3e8bbf2de29f7a466e7841c13faefe9dc8d1"

# Database connection URL
# Render / Supabase / Neon provides postgres:// or postgresql://
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "data" / "goldsea.db")).strip()
if not DATABASE_URL:
    if ENVIRONMENT == "production":
        DATABASE_URL = ""  # Will trigger production validation error
    else:
        # Normalize local SQLite path
        db_p = Path(DATABASE_PATH)
        db_p.parent.mkdir(parents=True, exist_ok=True)
        # Use absolute path for sqlite url so tests and subdirectories resolve properly
        DATABASE_URL = f"sqlite:///{db_p.resolve().as_posix()}"

# Email Service Configuration
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "").strip().lower()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@goldsea.ai").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587").strip() or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
SMTP_TLS = os.environ.get("SMTP_TLS", "true").strip().lower() in ("true", "1", "yes")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()

# If backend not explicitly set, determine from available credentials
if not EMAIL_BACKEND:
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        EMAIL_BACKEND = "smtp"
    elif RESEND_API_KEY:
        EMAIL_BACKEND = "resend"
    elif BREVO_API_KEY:
        EMAIL_BACKEND = "brevo"
    elif ENVIRONMENT != "production":
        EMAIL_BACKEND = "console"
    else:
        EMAIL_BACKEND = ""

# LLM Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview").strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free").strip()

APP_NAME = "GoldSea AI Chatbot"
APP_VERSION = "2.0.0"

def validate_production_config():
    """
    Validates required production environment variables.
    Fails fast with clear descriptive error messages naming any missing variable.
    Never silently falls back to SQLite or console email in production.
    """
    if ENVIRONMENT != "production":
        return

    missing = []

    if not SECRET_KEY or len(SECRET_KEY) < 32:
        missing.append("SECRET_KEY (must be a secure random string of at least 32 characters)")

    if not DATABASE_URL or not (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+psycopg2://")):
        missing.append("DATABASE_URL (must be a valid PostgreSQL connection string starting with postgresql://; SQLite is prohibited in production)")

    has_smtp = bool(SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM)
    has_resend = bool(RESEND_API_KEY and EMAIL_FROM)
    has_brevo = bool(BREVO_API_KEY and EMAIL_FROM)
    if not (has_smtp or has_resend or has_brevo):
        missing.append("Email Provider: Set SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM) OR Resend (RESEND_API_KEY, EMAIL_FROM) OR Brevo (BREVO_API_KEY, EMAIL_FROM)")

    if EMAIL_BACKEND == "console":
        missing.append("EMAIL_BACKEND cannot be 'console' in production; configure live SMTP, Resend, or Brevo")

    if not APP_BASE_URL or not APP_BASE_URL.startswith("http"):
        missing.append("APP_BASE_URL (must be set to your live Render application URL, e.g. https://goldsea-chatbot.onrender.com)")

    if missing:
        error_lines = ["\n[CRITICAL CONFIGURATION ERROR] Missing required production environment variables:"]
        for idx, item in enumerate(missing, 1):
            error_lines.append(f"  {idx}. {item}")
        error_lines.append("\nThe application has failed fast on startup to prevent data loss or insecure execution.\n")
        raise RuntimeError("\n".join(error_lines))
