import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")


class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()


async def connect_to_mongodb():
    if not MONGODB_URL:
        raise RuntimeError("MONGODB_URL is not set. Configure it in environment variables or .env.")

    db_instance.client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    await db_instance.client.admin.command("ping")
    db_instance.db = db_instance.client.cyberpunk_db


async def close_mongodb_connection():
    if db_instance.client:
        db_instance.client.close()
    db_instance.client = None
    db_instance.db = None