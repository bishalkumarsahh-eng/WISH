import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
MONGO_URI = os.getenv("MONGO_URI", "").strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or "development-secret-change-me"
PREVIEW_SECONDS = int(os.getenv("PREVIEW_SECONDS", "30"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0") or 0)
