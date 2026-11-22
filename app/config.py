import os

def _load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
DB_PATH = os.environ.get("DB_PATH", "civicpulse.db")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")

AI_DAILY_CALL_CAP = int(os.environ.get("AI_DAILY_CALL_CAP", "30"))
