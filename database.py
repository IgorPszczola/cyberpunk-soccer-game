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
    db_instance.client = AsyncIOMotorClient(MONGODB_URL)
    db_instance.db = db_instance.client.cyberpunk_db


async def close_mongodb_connection():
    if db_instance.client:
        db_instance.client.close()