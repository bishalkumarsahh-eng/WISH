import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
MONGO_URI = os.getenv("MONGO_URI", "").strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or "development-secret-change-me"
PREVIEW_MINUTES = int(os.getenv("PREVIEW_MINUTES", "2"))
