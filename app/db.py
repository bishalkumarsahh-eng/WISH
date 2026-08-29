from datetime import timezone
from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGO_URI

# tz_aware=True is important because website preview/publish expiry times are
# stored in MongoDB and compared against timezone-aware UTC datetimes.
client = (
    AsyncIOMotorClient(MONGO_URI, tz_aware=True, tzinfo=timezone.utc)
    if MONGO_URI
    else None
)
db = client["wishverse"] if client else None

async def setup_indexes():
    if db is None:
        raise RuntimeError("MONGO_URI is missing")
    await db.websites.create_index("slug", unique=True)
    await db.websites.create_index("owner_id")
    await db.websites.create_index("preview_token", unique=True, sparse=True)
    await db.users.create_index("telegram_id", unique=True)
    await db.payments.create_index("payload", unique=True)
    await db.payments.create_index("telegram_payment_charge_id", unique=True, sparse=True)
