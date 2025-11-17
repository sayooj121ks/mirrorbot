import telebot
from collections import defaultdict
from threading import Timer
from pymongo import MongoClient
import os
import time

# Configuration - using environment variables for security
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://sayoojsayoojks72_db_user:MXhCHQUIZeZk9aEH@cluster0.qocoeg0.mongodb.net/?appName=Cluster0")
TOKEN = os.getenv("BOT_TOKEN", "8406369208:AAG5LVhuDoVKVSutRwaUwsVFiBcFK805kmQ")

# Define your 2 source channels
SOURCE_CHANNELS = [-1003076383407, -1002990438747]  # Replace these with your channel IDs

# Initialize MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client["mirror_bot_db"]
    channels_col = db["channels"]
    print("✅ Connected to MongoDB successfully")
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")
    exit(1)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# Load channels from database
def load_channels():
    try:
        return [doc['chat_id'] for doc in channels_col.find()]
    except Exception as e:
        print(f"❌ Error loading channels: {e}")
        return []

def add_channel_to_db(chat_id, chat_title=None):
    try:
        if not channels_col.find_one({"chat_id": chat_id}):
            channels_col.insert_one({
                "chat_id": chat_id,
                "chat_title": chat_title or "Unknown",
                "added_at": time.time(),
                "is_source": chat_id in SOURCE_CHANNELS
            })
            return True
        return False
    except Exception as e:
        print(f"❌ Error adding channel: {e}")
        return False

def remove_channel_from_db(chat_id):
    try:
        result = channels_col.delete_one({"chat_id": chat_id})
        return result.deleted_count > 0
    except Exception as e:
        print(f"❌ Error removing channel: {e}")
        return False

# Initialize data
channels = load_channels()
media_groups = defaultdict(list)
media_group_timers = {}

print(f"📊 Loaded {len(channels)} channels")
print(f"🎯 Source channels: {SOURCE_CHANNELS}")

# ───────────────────────────────
# Commands
# ───────────────────────────────

@bot.channel_post_handler(commands=['add'])
def add_channel(message):
    chat_id = message.chat.id
    chat_title = getattr(message.chat, 'title', 'Unknown Channel')

    if chat_id not in channels:
        if add_channel_to_db(chat_id, chat_title):
            channels.append(chat_id)
            status = "🎯 Source Channel" if chat_id in SOURCE_CHANNELS else "📥 Destination Channel"
            bot.send_message(chat_id, f"✅ '{chat_title}' added! {status}")
        else:
            bot.send_message(chat_id, "❌ Could not add channel.")
    else:
        bot.send_message(chat_id, "ℹ Already added.")

@bot.channel_post_handler(commands=['remove'])
def remove_channel(message):
    chat_id = message.chat.id

    if chat_id in channels:
        if remove_channel_from_db(chat_id):
            channels.remove(chat_id)
            bot.send_message(chat_id, "✅ Channel removed.")
        else:
            bot.send_message(chat_id, "❌ Failed to remove.")
    else:
        bot.send_message(chat_id, "❌ Channel not found.")

@bot.channel_post_handler(commands=['list'])
def list_channels(message):
    try:
        all_ch = list(channels_col.find())
        if not all_ch:
            bot.send_message(message.chat.id, "📭 No channels added.")
            return

        response = "📊 **Registered Channels**:\n\n"
        for channel in all_ch:
            chat_id = channel.get("chat_id")
            title = channel.get("chat_title", "Unknown")
            icon = "🎯" if chat_id in SOURCE_CHANNELS else "📥"
            response += f"{icon} {title} (ID: {chat_id})\n"

        bot.send_message(message.chat.id, response)
    except:
        bot.send_message(message.chat.id, "❌ Error loading list.")

@bot.channel_post_handler(commands=['stats'])
def stats(message):
    total = len(channels)
    src = len([c for c in channels if c in SOURCE_CHANNELS])
    dst = total - src

    text = (
        f"📈 **Bot Stats:**\n"
        f"• Total Channels: {total}\n"
        f"• Source: {src} 🎯\n"
        f"• Destination: {dst} 📥\n"
        f"• MongoDB: Connected\n"
        f"• Bot: Running"
    )
    bot.send_message(message.chat.id, text)

@bot.channel_post_handler(commands=['start', 'help'])
def help_command(message):
    bot.send_message(message.chat.id, """
🤖 **Mirror Bot Commands**

`/add` – Add this channel
`/remove` – Remove channel
`/list` – Show channels
`/stats` – Show bot stats
`/help` – Help

**How it works:**
- 🎯 Source channels → mirror to all destination channels.
- 📥 Add bot as admin in each channel and send /add.
""")

# ───────────────────────────────
# Media Groups
# ───────────────────────────────

def send_media_group_to_channel(chat, group):
    try:
        media = []
        for msg in group:
            ctype = msg.content_type
            caption = getattr(msg, "caption", "")

            if ctype == "photo":
                media.append(telebot.types.InputMediaPhoto(msg.photo[-1].file_id, caption=caption if not media else None))
            elif ctype == "video":
                media.append(telebot.types.InputMediaVideo(msg.video.file_id, caption=caption if not media else None))

        if media:
            bot.send_media_group(chat, media)
    except Exception as e:
        print("❌ Media group error:", e)

def process_media_group(mgid, source):
    if mgid not in media_groups:
        return

    messages = media_groups[mgid]
    del media_groups[mgid]

    targets = [c for c in channels if c not in SOURCE_CHANNELS]
    for chat in targets:
        send_media_group_to_channel(chat, messages)

# ───────────────────────────────
# Single Messages
# ───────────────────────────────

def send_to_channel(chat, msg):
    try:
        ctype = msg.content_type

        if ctype == 'text':
            bot.send_message(chat, msg.text)

        elif ctype == 'photo':
            bot.send_photo(chat, msg.photo[-1].file_id, caption=msg.caption)

        elif ctype == 'video':
            bot.send_video(chat, msg.video.file_id, caption=msg.caption)

        elif ctype == 'document':
            bot.send_document(chat, msg.document.file_id, caption=msg.caption)

        elif ctype == 'audio':
            bot.send_audio(chat, msg.audio.file_id, caption=msg.caption)

        elif ctype == 'voice':
            bot.send_voice(chat, msg.voice.file_id)

        elif ctype == 'sticker':
            bot.send_sticker(chat, msg.sticker.file_id)

    except Exception as e:
        print("❌ Error sending message:", e)

@bot.channel_post_handler(content_types=[
    'text','photo','video','document','audio','voice','animation',
    'sticker','video_note','poll','location','contact'
])
def mirror(message):
    source = message.chat.id
    if source not in SOURCE_CHANNELS:
        return

    targets = [c for c in channels if c not in SOURCE_CHANNELS]

    mgid = getattr(message, "media_group_id", None)
    if mgid:
        media_groups[mgid].append(message)
        if mgid in media_group_timers:
            media_group_timers[mgid].cancel()

        timer = Timer(1, process_media_group, [mgid, source])
        media_group_timers[mgid] = timer
        timer.start()
    else:
        for chat in targets:
            send_to_channel(chat, message)

# ───────────────────────────────
# Start Bot
# ───────────────────────────────

def start_polling():
    while True:
        try:
            print("🟢 Bot Polling Started")
            bot.polling(none_stop=True)
        except Exception as e:
            print("🔴 Crash:", e)
            time.sleep(5)

if __name__ == "__main__":
    print("🚀 Mirror Bot Starting...")
    start_polling()









