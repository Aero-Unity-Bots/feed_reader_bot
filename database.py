import datetime
import pytz
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client["feed_reader_db"]
subscriptions_col = db["subscriptions"]
users_col = db["users"]

async def add_subscription(user_id: int, feed_url: str, feed_title: str):
    exists = await subscriptions_col.find_one({"user_id": user_id, "feed_url": feed_url})
    if exists:
        return False
    await subscriptions_col.insert_one({
        "user_id": user_id,
        "feed_url": feed_url,
        "feed_title": feed_title,
        "last_entry_link": None
    })
    return True

async def get_user_subscriptions(user_id: int):
    return await subscriptions_col.find({"user_id": user_id}).to_list(length=None)

async def remove_subscription_db(sub_id: str, user_id: int):
    from bson.objectid import ObjectId
    result = await subscriptions_col.delete_one({"_id": ObjectId(sub_id), "user_id": user_id})
    return result.deleted_count > 0

async def get_all_unique_feeds():
    # Returns distinct feed URLs being tracked
    return await subscriptions_col.distinct("feed_url")

async def get_subscribers_for_feed(feed_url: str):
    return await subscriptions_col.find({"feed_url": feed_url}).to_list(length=None)

async def update_last_entry(feed_url: str, entry_link: str):
    await subscriptions_col.update_many(
        {"feed_url": feed_url},
        {"$set": {"last_entry_link": entry_link}}
    )

async def add_user(user_id: int, name: str, username: str):
    exists = await users_col.find_one({"user_id": user_id})
    if not exists:
        joined_str = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
        await users_col.insert_one({
            "user_id": user_id,
            "name": name,
            "username": username,
            "joined_date": joined_str
        })

async def get_total_users_count():
    return await users_col.count_documents({})

async def get_latest_user():
    return await users_col.find_one(sort=[("_id", -1)])
