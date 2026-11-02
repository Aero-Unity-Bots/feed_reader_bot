import asyncio
import datetime
from threading import Thread
import pytz
from flask import Flask
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import API_ID, API_HASH, BOT_TOKEN, PORT, OWNER_ID
import database as db

# --- Flask Web Server (For Render Web Service Health Checks) ---
web_app = Flask(__name__)

@web_app.route("/")
def health_check():
    return "Telegram Channel Feed Bot is running active!", 200

def run_flask():
    web_app.run(host="0.0.0.0", port=PORT)

# --- Pyrogram Bot & Scheduler Setup ---
bot = Client("telegram_feed_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler(timezone=pytz.UTC)

# --- Listen for New Posts in Tracked Channels ---
@bot.on_message(filters.channel)
async def channel_post_listener(_, message: Message):
    try:
        chat = message.chat
        channel_username = chat.username
        if not channel_username:
            return

        # Find all users subscribed to this channel
        subscribers = await db.get_subscribers_for_channel(channel_username)
        for sub in subscribers:
            try:
                # Copy the owner's exact post (text, photos, videos, buttons) to the user
                await message.copy(chat_id=sub["user_id"])
            except Exception as e:
                print(f"Failed to forward post to user {sub['user_id']}: {e}")
    except Exception as e:
        print(f"Error in channel post listener: {e}")

# --- Bot Command Handlers ---
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.first_name, user.username)

    welcome_text = (
        f"👋 **Hello {user.first_name}!**\n\n"
        "I am your automated **Telegram Channel Feed Bot**.\n"
        "Send me a channel username (e.g., `/add @Aero_Unity`) or link to subscribe, and I will notify you instantly whenever the owner posts!\n\n"
        "**Commands:**\n"
        "• `/add @channel` - Subscribe to a Telegram channel\n"
        "• `/feeds` - View your active channel subscriptions\n"
        "• `/help` - Learn how to use the bot\n\n"
        "Powered By @Aero_Unity"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Updates", url="https://t.me/Aero_Unity"),
            InlineKeyboardButton("ℹ️ About", callback_data="menu_about")
        ]
    ])
    await message.reply_text(welcome_text, reply_markup=keyboard)

@bot.on_message(filters.command("help") & filters.private)
async def help_cmd(_, message: Message):
    help_text = (
        "📖 **Channel Feed Help Guide**\n\n"
        "1️⃣ **Important Requirement:**\n"
        "The bot **must** be added as an administrator in the channel so it can read new posts.\n\n"
        "2️⃣ **How to subscribe:**\n"
        "Send `/add @Aero_Unity` or paste the channel link.\n\n"
        "3️⃣ **Managing Subscriptions:**\n"
        "Use `/feeds` to see all channels you are following and remove any you no longer want."
    )
    await message.reply_text(help_text)

@bot.on_message(filters.command("add") & filters.private)
async def add_channel_cmd(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("⚠️ Please provide a channel username.\n\n**Example:** `/add @Aero_Unity`")
        return
    
    raw_input = args[1].strip()
    # Extract username from link or handle @ format
    if "t.me/" in raw_input:
        channel_uname = raw_input.split("t.me/")[-1].split("/")[0]
    else:
        channel_uname = raw_input.replace("@", "")

    try:
        chat = await bot.get_chat(channel_uname)
        if chat.type.name != "CHANNEL":
            await message.reply_text("⚠️ That username does not belong to a public Telegram channel.")
            return
        
        channel_title = chat.title
        success = await db.add_channel_subscription(message.from_user.id, channel_uname, channel_title)
        
        if success:
            await message.reply_text(
                f"✅ **Successfully Subscribed!**\n\n"
                f"📌 **Channel:** {channel_title}\n"
                f"🔗 `@{channel_uname}`\n\n"
                "You will receive all future posts from this channel right here!"
            )
        else:
            await message.reply_text("⚠️ You are already subscribed to this channel!")
            
    except Exception as e:
        await message.reply_text(f"⚠️ Could not access channel. Make sure the username is correct and the bot is added to the channel. ({e})")

@bot.on_message(filters.command("feeds") & filters.private)
async def feeds_cmd(_, message: Message):
    subs = await db.get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.reply_text("📥 You have no active channel subscriptions.\nUse `/add @channel` to subscribe!")
        return

    text = "📋 **Your Active Channel Subscriptions:**\n\n"
    buttons = []
    for s in subs:
        text += f"• **{s['channel_title']}** (`@{s['channel_username']}`)\n"
        buttons.append([InlineKeyboardButton(f"❌ Unsubscribe: @{s['channel_username']}", callback_data=f"del_{str(s['_id'])}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_message(filters.command("stats") & filters.private)
async def stats_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("⚠️ This command is restricted to the bot owner only.")
        return

    total_users = await db.get_total_users_count()
    all_users = await db.get_all_users()
    current_time = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')

    stats_text = (
        f"📊 **Bot Usage & All Users Stats**\n\n"
        f"👥 **Total Users Started Bot:** `{total_users}`\n"
        f"⏰ **Current Time:** `{current_time}`\n\n"
        f"📋 **User List:**\n"
    )

    for idx, u in enumerate(all_users, 1):
        u_name = u.get("name", "N/A")
        u_username = f"@{u.get('username')}" if u.get('username') else "None"
        u_id = u.get("user_id", "N/A")
        u_joined = u.get("joined_date", "N/A")
        
        stats_text += f"\n{idx}. **{u_name}** ({u_username})\n   🆔 ID: `{u_id}` | 📅 Joined: `{u_joined}`"
        
        # Telegram message length limit check (prevent long message errors if you have hundreds of users)
        if len(stats_text) > 3800:
            stats_text += "\n\n_...and more users (list truncated due to length)_"
            break

    close_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Close", callback_data="menu_close")]
    ])
    await message.reply_text(stats_text, reply_markup=close_kb)

@bot.on_callback_query(filters.regex(r"^(del_|menu_)"))
async def callback_handler(_, query: CallbackQuery):
    data = query.data
    if data.startswith("del_"):
        _, sub_id = data.split("_")
        removed = await db.remove_subscription_db(sub_id, query.from_user.id)
        if removed:
            await query.answer("Unsubscribed successfully!", show_alert=True)
            await query.message.delete()
        else:
            await query.answer("Subscription not found.", show_alert=True)
            
    elif data == "menu_about":
        about_text = (
            "🤖 **About Channel Feed Bot**\n\n"
            "• **My name:** @TheFeedReaderBot (Telegram Edition)\n"
            "• **Library:** Pyrogram\n"
            "• **Language:** Python 3.11+\n"
            "• **Version:** 2.0.0\n"
            "• **Updates:** @Aero_Unity\n"
            "• **Developer:** Mohammed (@Mr_Mohammed_29)\n\n"
            "Instant Telegram channel post forwarding bot!"
        )
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="menu_home")]
        ])
        await query.message.edit_text(about_text, reply_markup=back_kb)
        await query.answer()

    elif data == "menu_home":
        welcome_text = (
            f"👋 **Hello {query.from_user.first_name}!**\n\n"
            "I am your automated **Telegram Channel Feed Bot**.\n"
            "Send me a channel username (e.g., `/add @Aero_Unity`) or link to subscribe, and I will notify you instantly whenever the owner posts!\n\n"
            "**Commands:**\n"
            "• `/add @channel` - Subscribe to a Telegram channel\n"
            "• `/feeds` - View your active channel subscriptions\n"
            "• `/help` - Learn how to use the bot\n\n"
            "Powered By @Aero_Unity"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Updates", url="https://t.me/Aero_Unity"),
                InlineKeyboardButton("ℹ️ About", callback_data="menu_about")
            ]
        ])
        await query.message.edit_text(welcome_text, reply_markup=keyboard)
        await query.answer()

    elif data == "menu_close":
        await query.message.delete()
        await query.answer("Closed!")

async def main():
    Thread(target=run_flask, daemon=True).start()
    scheduler.start()
    
    await bot.start()
    print("Telegram Channel Feed Bot is up and running!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
