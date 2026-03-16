"""
Premium user management — stored in MongoDB Atlas.
Collection: bot_db.premium_users
Document shape: { _id: user_id (int), expiry: datetime (UTC) }

Uses a module-level singleton MongoClient so all concurrent requests
share one connection pool instead of opening a new connection per call.
"""

import logging
import os
from datetime import datetime, timedelta

from pymongo import MongoClient
from pymongo.collection import Collection

logger = logging.getLogger(__name__)

OWNER_ID = 8002803133

_client: MongoClient | None = None


def _get_collection() -> Collection:
    global _client
    if _client is None:
        uri = os.environ.get("mongodb+srv://sakshamranjan7:8wBCaYilCTlgdNV3@cluster0.h184m7m.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set.")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        logger.info("MongoDB client initialised")
    return _client["bot_db"]["premium_users"]


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_premium(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    try:
        col = _get_collection()
        doc = col.find_one({"_id": user_id})
        if not doc:
            return False
        expiry: datetime = doc["expiry"]
        if datetime.utcnow() < expiry:
            return True
        col.delete_one({"_id": user_id})
        return False
    except Exception as e:
        logger.error("MongoDB is_premium check failed: %s", e)
        return False


def grant_premium(user_id: int, months: int) -> datetime:
    col = _get_collection()
    doc = col.find_one({"_id": user_id})
    if doc:
        base = doc["expiry"]
        if base < datetime.utcnow():
            base = datetime.utcnow()
    else:
        base = datetime.utcnow()
    expiry = base + timedelta(days=30 * months)
    col.update_one(
        {"_id": user_id},
        {"$set": {"expiry": expiry}},
        upsert=True,
    )
    logger.info("Granted %d month(s) premium to user %d, expires %s", months, user_id, expiry)
    return expiry


def get_expiry(user_id: int) -> datetime | None:
    try:
        col = _get_collection()
        doc = col.find_one({"_id": user_id})
        return doc["expiry"] if doc else None
    except Exception as e:
        logger.error("MongoDB get_expiry failed: %s", e)
        return None


def list_premium_users() -> list[tuple[int, datetime]]:
    try:
        col = _get_collection()
        now = datetime.utcnow()
        docs = col.find({"expiry": {"$gt": now}}).sort("expiry", 1)
        return [(doc["_id"], doc["expiry"]) for doc in docs]
    except Exception as e:
        logger.error("MongoDB list_premium_users failed: %s", e)
        return []
