from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


class DatabaseUnavailable(RuntimeError):
    """Raised instead of silently persisting application data in process memory."""


mongo_client: AsyncIOMotorClient | None = None
database: Any = None
mongo_available = False


async def connect_to_mongodb() -> None:
    global mongo_client, database, mongo_available
    try:
        mongo_client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=1200)
        await mongo_client.admin.command("ping")
        database = mongo_client[settings.mongodb_database]
        mongo_available = True
    except Exception:
        if mongo_client:
            mongo_client.close()
        mongo_client = None
        database = None
        mongo_available = False


async def close_mongodb_connection() -> None:
    if mongo_client:
        mongo_client.close()


def collection(name: str) -> Any:
    if not mongo_available or database is None:
        raise DatabaseUnavailable("MongoDB is unavailable. Start MongoDB and retry; no data was saved.")
    return database[name]