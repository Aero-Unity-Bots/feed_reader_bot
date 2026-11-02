import datetime
import pytz
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_feed_db"]
subscriptions_col = db["channel_subscriptions"]
users_col = db["users"]

async def add_channel_subscription(user_id: int, channel_username: str, channel_title: str):
    exists = await subscriptions_col.find_one({"user_id": user_id, "channel_username": channel_username})
    if exists:
        return False
    await subscriptions_col.insert_one({
        "user_id": user_id,
        "channel_username": channel_username.lower().replace("@", ""),
        "channel_title": channel_title
    })
    return True

async def get_user_subscriptions(user_id: int):
    return await subscriptions_col.find({"user_id": user_id}).to_list(length=None)

async def remove_subscription_db(sub_id: str, user_id: int):
    from bson.objectid import ObjectId
    result = await subscriptions_col.delete_one({"_id": ObjectId(sub_id), "user_id": user_id})
    return result.deleted_count > 0

async def get_subscribers_for_channel(channel_username: str):
    clean_uname = channel_username.lower().replace("@", "")
    return await subscriptions_col.find({"channel_username": clean_uname}).to_list(length=None)

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

async def get_all_users():
    return await users_col.find({}).to_list(length=None)

async def get_total_users_count():
    return await users_col.count_documents({})

async def get_latest_user():
    return await users_col.find_one(sort=[("_id", -1)])
