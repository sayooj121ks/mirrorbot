import telebot
from collections import defaultdict
from threading import Timer
from pymongo import MongoClient
import os
import time
from flask import Flask
import threading

# Configuration - using environment variables for security
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://sayoojsayoojks72_db_user:MXhCHQUIZeZk9aEH@cluster0.qocoeg0.mongodb.net/?appName=Cluster0")
TOKEN = os.getenv("BOT_TOKEN", "8406369208:AAG5LVhuDoVKVSutRwaUwsVFiBcFK805kmQ")

# Define your 2 source channels that will mirror to others
SOURCE_CHANNELS = [-1003076383407, -1002990438747]  # Replace with your actual channel IDs

# Initialize Flask app for health checks
app = Flask(__name__)

@app.route('/')
def health_check():
    return {
        "status": "online",
        "bot": "running",
        "channels": len(channels),
        "source_channels": SOURCE_CHANNELS,
        "timestamp": time.time()
    }

@app.route('/health')
def health():
    return "✅ Bot is healthy and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


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
        print(f"❌ Error adding channel to DB: {e}")
        return False

def remove_channel_from_db(chat_id):
    try:
        result = channels_col.delete_one({"chat_id": chat_id})
        return result.deleted_count > 0
    except Exception as e:
        print(f"❌ Error removing channel from DB: {e}")
        return False

# Initialize data structures
channels = load_channels()
media_groups = defaultdict(list)
media_group_timers = {}

print(f"📊 Loaded {len(channels)} channels from database")
print(f"🎯 Source channels: {SOURCE_CHANNELS}")

# ───────────────────────────────
# Bot Commands
# ───────────────────────────────

@bot.channel_post_handler(commands=['add'])
def add_channel_command(message):
    chat_id = message.chat.id
    chat_title = getattr(message.chat, 'title', 'Unknown Channel')
    
    if chat_id not in channels:
        if add_channel_to_db(chat_id, chat_title):
            channels.append(chat_id)
            # Check if this is a source channel
            if chat_id in SOURCE_CHANNELS:
                status = " (Source Channel 🎯)"
            else:
                status = " (Destination Channel)"
                
            bot.send_message(chat_id, f"✅ Channel '{chat_title}' added!{status}\nTotal channels: {len(channels)}")
            print(f"✅ Added channel: {chat_id} ({chat_title}){status}")
        else:
            bot.send_message(chat_id, "❌ Failed to add channel to database.")
    else:
        bot.send_message(chat_id, "ℹ️ Channel already added.")

@bot.channel_post_handler(commands=['remove'])
def remove_channel_command(message):
    chat_id = message.chat.id
    
    if chat_id in channels:
        if remove_channel_from_db(chat_id):
            channels.remove(chat_id)
            bot.send_message(chat_id, "✅ Channel removed from database.")
            print(f"✅ Removed channel: {chat_id}")
        else:
            bot.send_message(chat_id, "❌ Failed to remove channel from database.")
    else:
        bot.send_message(chat_id, "❌ Channel not found in database.")

@bot.channel_post_handler(commands=['list'])
def list_channels_command(message):
    try:
        all_channels = list(channels_col.find())
        if not all_channels:
            bot.send_message(message.chat.id, "📭 No channels registered yet.")
            return
        
        response = "📊 **Registered Channels:**\n\n"
        for channel in all_channels:
            title = channel.get('chat_title', 'Unknown')
            chat_id = channel.get('chat_id', 'N/A')
            is_source = "🎯 " if chat_id in SOURCE_CHANNELS else "📥 "
            response += f"{is_source} {title} (ID: {chat_id})\n"
        
        bot.send_message(message.chat.id, response)
    except Exception as e:
        print(f"❌ Error listing channels: {e}")
        bot.send_message(message.chat.id, "❌ Error retrieving channel list.")

@bot.channel_post_handler(commands=['stats'])
def stats_command(message):
    total_channels = len(channels)
    source_count = len([chat for chat in channels if chat in SOURCE_CHANNELS])
    destination_count = total_channels - source_count
    
    response = f"📈 **Bot Statistics:**\n\n"
    response += f"• Total Channels: {total_channels}\n"
    response += f"• Source Channels: {source_count} 🎯\n"
    response += f"• Destination Channels: {destination_count} 📥\n"
    response += f"• Database: Connected ✅\n"
    response += f"• Bot: Running ✅"
    
    bot.send_message(message.chat.id, response)

@bot.channel_post_handler(commands=['start', 'help'])
def help_command(message):
    help_text = """
🤖 **Mirror Bot Commands:**

`/add` - Add this channel to mirroring
`/remove` - Remove this channel from mirroring  
`/list` - List all registered channels
`/stats` - Show bot statistics
`/help` - Show this help message

**How it works:**
- 🎯 **Source Channels**: Messages from these channels are mirrored to all destination channels
- 📥 **Destination Channels**: Receive mirrored messages from source channels
- Add bot as admin to all channels
- Send `/add` in each channel
- Only messages from source channels will be mirrored
"""
    bot.send_message(message.chat.id, help_text)

# ───────────────────────────────
# Media Group Handling
# ───────────────────────────────

def send_media_group_to_channel(target_chat, media_group_messages):
    try:
        if not media_group_messages:
            return
            
        media_array = []
        
        for msg in media_group_messages:
            ctype = msg.content_type
            caption = getattr(msg, 'caption', '') or ""
            caption_entities = getattr(msg, 'caption_entities', None)
            
            if ctype == 'photo' and hasattr(msg, 'photo') and msg.photo:
                file_id = msg.photo[-1].file_id
                media_array.append(telebot.types.InputMediaPhoto(
                    media=file_id,
                    caption=caption if len(media_array) == 0 else None,
                    caption_entities=caption_entities if len(media_array) == 0 else None
                ))
                
            elif ctype == 'video' and hasattr(msg, 'video') and msg.video:
                media_array.append(telebot.types.InputMediaVideo(
                    media=msg.video.file_id,
                    caption=caption if len(media_array) == 0 else None,
                    caption_entities=caption_entities if len(media_array) == 0 else None
                ))
        
        if media_array:
            bot.send_media_group(target_chat, media_array)
            print(f"✅ Sent media group with {len(media_array)} items to {target_chat}")
            
    except Exception as e:
        print(f"❌ Failed to send media group to {target_chat}: {e}")

def process_media_group(media_group_id, source_chat):
    if media_group_id in media_groups:
        messages = media_groups[media_group_id]
        print(f"🔄 Processing media group {media_group_id} with {len(messages)} messages from {source_chat}")
        
        # Clean up
        del media_groups[media_group_id]
        if media_group_id in media_group_timers:
            del media_group_timers[media_group_id]
        
        # Mirror to destination channels only (exclude source channels)
        if source_chat in SOURCE_CHANNELS:
            target_channels = [chat for chat in channels if chat not in SOURCE_CHANNELS]
            for target_chat in target_channels:
                send_media_group_to_channel(target_chat, messages)

# ───────────────────────────────
# Message Handling
# ───────────────────────────────

def send_to_channel(target_chat, message):
    try:
        ctype = message.content_type
        caption = getattr(message, 'caption', '') or ""
        caption_entities = getattr(message, 'caption_entities', None)
        entities = getattr(message, 'entities', None)

        if ctype == 'text':
            bot.send_message(target_chat, message.text, entities=entities)

        elif ctype == 'photo':
            file_id = message.photo[-1].file_id if message.photo else None
            if file_id:
                bot.send_photo(target_chat, file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'video':
            if hasattr(message, 'video') and message.video:
                bot.send_video(target_chat, message.video.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'document':
            if hasattr(message, 'document') and message.document:
                bot.send_document(target_chat, message.document.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'audio':
            if hasattr(message, 'audio') and message.audio:
                bot.send_audio(target_chat, message.audio.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'voice':
            if hasattr(message, 'voice') and message.voice:
                bot.send_voice(target_chat, message.voice.file_id, caption=caption)

        elif ctype == 'animation':
            if hasattr(message, 'animation') and message.animation:
                bot.send_animation(target_chat, message.animation.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'sticker':
            if hasattr(message, 'sticker') and message.sticker:
                bot.send_sticker(target_chat, message.sticker.file_id)

        elif ctype == 'video_note':
            if hasattr(message, 'video_note') and message.video_note:
                bot.send_video_note(target_chat, message.video_note.file_id)

        elif ctype == 'poll':
            if hasattr(message, 'poll') and message.poll:
                bot.send_poll(target_chat, message.poll.question, 
                             [opt.text for opt in message.poll.options])

        elif ctype == 'location':
            if hasattr(message, 'location') and message.location:
                bot.send_location(target_chat, message.location.latitude, message.location.longitude)

        elif ctype == 'contact':
            if hasattr(message, 'contact') and message.contact:
                bot.send_contact(target_chat, message.contact.phone_number, message.contact.first_name)

        else:
            print(f"⚠️ Unsupported type: {ctype}")
            if hasattr(message, 'text') and message.text:
                bot.send_message(target_chat, f"[{ctype}] {message.text}")

    except Exception as e:
        print(f"❌ Failed to send {ctype} to {target_chat}: {e}")

@bot.channel_post_handler(content_types=[
    'text', 'photo', 'video', 'document', 'audio', 'voice', 
    'animation', 'sticker', 'video_note', 'poll', 'location', 'contact'
])
def mirror_message(message):
    source_chat = message.chat.id
    
    # Only mirror if message comes from one of the source channels
    if source_chat not in SOURCE_CHANNELS:
        return
    
    # Only mirror to channels that are in the database AND not source channels
    target_channels = [chat for chat in channels if chat not in SOURCE_CHANNELS]
    
    media_group_id = getattr(message, 'media_group_id', None)
    
    if media_group_id:
        # Handle media group
        media_groups[media_group_id].append(message)
        
        # Reset timer
        if media_group_id in media_group_timers:
            media_group_timers[media_group_id].cancel()
        
        timer = Timer(1.0, process_media_group, [media_group_id, source_chat])
        media_group_timers[media_group_id] = timer
        timer.start()
        
        print(f"📦 Added to media group {media_group_id} (total: {len(media_groups[media_group_id])})")
        
    else:
        # Handle single message
        print(f"🎯 Mirroring {message.content_type} from source channel {source_chat} to {len(target_channels)} destination channels")
        for target_chat in target_channels:
            send_to_channel(target_chat, message)

# ───────────────────────────────
# Error Handling & Startup
# ───────────────────────────────

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Handle non-channel messages"""
    if message.chat.type != 'channel':
        bot.reply_to(message, "🤖 This bot works only in channels. Add me to a channel as admin and use /add command.")

def start_polling():
    """Start bot with error handling and restart logic"""
    while True:
        try:
            print("🟢 Starting bot polling...")
            print(f"📊 Tracking {len(channels)} channels")
            print(f"🎯 Source channels: {len([c for c in channels if c in SOURCE_CHANNELS])}")
            print(f"📥 Destination channels: {len([c for c in channels if c not in SOURCE_CHANNELS])}")
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            print(f"🔴 Bot crashed: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("🚀 Mirror Bot Starting...")
    print("🌐 Health check available at port 8080")
    print("✅ MongoDB:", "Connected" if client else "Disconnected")
    print("✅ Bot Token:", "Loaded" if TOKEN else "Missing")
    print("✅ Channels:", len(channels))
    start_polling()






