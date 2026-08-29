from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI) if MONGO_URI else None
db = client["wishverse"] if client else None

async def setup_indexes():
    if db is None:
        return
    await db.websites.create_index("slug", unique=True)
    await db.websites.create_index([("owner_id", 1)])
    await db.payments.create_index("telegram_payment_charge_id", unique=True, sparse=True)
    await db.users.create_index("telegram_id", unique=True)
