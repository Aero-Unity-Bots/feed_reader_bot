import asyncio
import datetime
from threading import Thread
import feedparser
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
    return "Feed Reader Bot is running active!", 200

def run_flask():
    web_app.run(host="0.0.0.0", port=PORT)

# --- Pyrogram Bot & Scheduler Setup ---
bot = Client("feed_reader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler(timezone=pytz.UTC)

# --- Background RSS Polling Job ---
async def check_rss_feeds():
    try:
        feed_urls = await db.get_all_unique_feeds()
        for f_url in feed_urls:
            parsed = feedparser.parse(f_url)
            if not parsed.entries:
                continue
            
            latest_entry = parsed.entries[0]
            entry_title = latest_entry.get("title", "No Title")
            entry_link = latest_entry.get("link", f_url)
            feed_title = parsed.feed.get("title", f_url)

            subscribers = await db.get_subscribers_for_feed(f_url)
            for sub in subscribers:
                # If last_entry_link is None, initialize it without spamming old posts
                if sub.get("last_entry_link") is None:
                    await db.update_last_entry(f_url, entry_link)
                    continue

                if sub.get("last_entry_link") != entry_link:
                    # New post detected! Send update to user
                    try:
                        msg = (
                            f"📰 **New Update from {feed_title}**\n\n"
                            f"📌 **{entry_title}**\n\n"
                            f"🔗 [Read Full Article]({entry_link})"
                        )
                        await bot.send_message(chat_id=sub["user_id"], text=msg, disable_web_page_preview=False)
                    except Exception as e:
                        print(f"Failed to send update to {sub['user_id']}: {e}")

            # Update tracked entry for this feed url
            await db.update_last_entry(f_url, entry_link)
    except Exception as e:
        print(f"Error in RSS polling job: {e}")

# --- Bot Command Handlers ---
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.first_name, user.username)

    welcome_text = (
        f"👋 **Hello {user.first_name}!**\n\n"
        "I am your automated **RSS & Blog Feed Reader Bot**.\n"
        "Send me any RSS feed URL or use /add to subscribe to your favorite blogs and sites, and I'll notify you instantly when new content publishes!\n\n"
        "**Commands:**\n"
        "• `/add <rss_url>` - Subscribe to a feed\n"
        "• `/feeds` - View your active subscriptions\n"
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
        "📖 **Feed Reader Help Guide**\n\n"
        "1️⃣ **How to subscribe:**\n"
        "Send `/add https://example.com/rss` or just paste any valid RSS/Atom feed URL.\n\n"
        "2️⃣ **Managing Subscriptions:**\n"
        "Use `/feeds` to see all feeds you are following and remove any you no longer want.\n\n"
        "3️⃣ **Automated Checks:**\n"
        "I check all registered feeds periodically in the background and send you instant updates!"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.command("add") & filters.private)
async def add_feed_cmd(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("⚠️ Please provide an RSS URL.\n\n**Example:** `/add https://news.ycombinator.com/rss`")
        return
    
    feed_url = args[1].strip()
    await process_and_add_feed(message, feed_url)

@bot.on_message(filters.command("feeds") & filters.private)
async def feeds_cmd(_, message: Message):
    subs = await db.get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.reply_text("📥 You have no active RSS subscriptions.\nUse `/add <url>` to subscribe!")
        return

    text = "📋 **Your Active Feed Subscriptions:**\n\n"
    buttons = []
    for s in subs:
        text += f"• **{s['feed_title']}**\n  `{s['feed_url']}`\n\n"
        buttons.append([InlineKeyboardButton(f"❌ Unsubscribe: {s['feed_title'][:15]}...", callback_data=f"del_{str(s['_id'])}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_message(filters.command("stats") & filters.private)
async def stats_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("⚠️ This command is restricted to the bot owner only.")
        return

    total_users = await db.get_total_users_count()
    latest_user = await db.get_latest_user()

    if latest_user:
        u_name = latest_user.get("name", "N/A")
        u_username = f"@{latest_user.get('username')}" if latest_user.get('username') else "None"
        u_id = latest_user.get("user_id", "N/A")
        u_joined = latest_user.get("joined_date", "N/A")
    else:
        u_name = message.from_user.first_name
        u_username = f"@{message.from_user.username}" if message.from_user.username else "None"
        u_id = message.from_user.id
        u_joined = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d')

    current_time = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')

    stats_text = (
        f"📊 **Feed Reader Bot Stats**\n\n"
        f"👥 **Total Users Started Bot:** `{total_users}`\n\n"
        f"👤 **Latest User Name:** {u_name}\n"
        f"🔗 **Latest Username:** {u_username}\n"
        f"🆔 **Latest User ID:** `{u_id}`\n"
        f"📅 **Joined Date:** {u_joined}\n"
        f"⏰ **Current Time:** {current_time}"
    )
    
    close_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Close", callback_data="menu_close")]
    ])
    await message.reply_text(stats_text, reply_markup=close_kb)

async def process_and_add_feed(message: Message, feed_url: str):
    parsed = feedparser.parse(feed_url)
    if not parsed.bozo and not parsed.entries:
        await message.reply_text("⚠️ Could not parse valid RSS feed data from this URL. Please verify the link.")
        return
    
    feed_title = parsed.feed.get("title", feed_url)
    success = await db.add_subscription(message.from_user.id, feed_url, feed_title)
    
    if success:
        await message.reply_text(f"✅ **Successfully Subscribed!**\n\n📌 **Feed:** {feed_title}\n🔗 `{feed_url}`\n\nYou will receive updates here as soon as new articles publish.")
    else:
        await message.reply_text("⚠️ You are already subscribed to this RSS feed!")

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
            "🤖 **About Feed Reader Bot**\n\n"
            "• **My name:** @TheFeedReaderBot (Custom instance)\n"
            "• **Library:** Pyrogram & Feedparser\n"
            "• **Language:** Python 3.11+\n"
            "• **Version:** 1.0.0\n"
            "• **Updates:** @Aero_Unity\n"
            "• **Developer:** Mohammed (@Mr_Mohammed_29)\n\n"
            "An RSS and blog syndication reader built for instant Telegram delivery!"
        )
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="menu_home")]
        ])
        await query.message.edit_text(about_text, reply_markup=back_kb)
        await query.answer()

    elif data == "menu_home":
        welcome_text = (
            f"👋 **Hello {query.from_user.first_name}!**\n\n"
            "I am your automated **RSS & Blog Feed Reader Bot**.\n"
            "Send me any RSS feed URL or use /add to subscribe to your favorite blogs and sites, and I'll notify you instantly when new content publishes!\n\n"
            "**Commands:**\n"
            "• `/add <rss_url>` - Subscribe to a feed\n"
            "• `/feeds` - View your active subscriptions\n"
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
    # Start Web Server for Render
    Thread(target=run_flask, daemon=True).start()
    
    # Schedule RSS check every 10 minutes
    scheduler.add_job(check_rss_feeds, 'interval', minutes=10)
    scheduler.start()
    
    # Start Telegram Bot
    await bot.start()
    print("Feed Reader Bot is up and running!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
