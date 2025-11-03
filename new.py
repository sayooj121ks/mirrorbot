import telebot

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://sayoojsayoojks72_db_user:MXhCHQUIZeZk9aEH@cluster0.qocoeg0.mongodb.net/?appName=Cluster0"
DB_NAME = "mirror_bot"
COLLECTION_NAME = "channels"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]


TOKEN = "8406369208:AAG5LVhuDoVKVSutRwaUwsVFiBcFK805kmQ"
bot = telebot.TeleBot(TOKEN)




channels = [doc["chat_id"] for doc in collection.find()]
print(f"Loaded {len(channels)} channels from MongoDB.")

# ───────────────────────────────
# Command: /add → Add this channel
# ───────────────────────────────
@bot.channel_post_handler(commands=['add'])
def add_channel(message):
    chat_id = message.chat.id
    if chat_id not in channels:
        channels.append(chat_id)
        collection.insert_one({"chat_id": chat_id})
        bot.send_message(chat_id, f"✅ Channel added and saved!\nTotal channels: {len(channels)}")
        print(f"Added channel: {chat_id}")
    else:
        bot.send_message(chat_id, "ℹ️ Channel already added.")


# ───────────────────────────────
# Function: Send message manually to target
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
            # Handle photo messages (with or without caption)
            file_id = message.photo[-1].file_id if message.photo else None
            if file_id:
                bot.send_photo(target_chat, file_id, caption=caption, caption_entities=caption_entities)
            else:
                bot.send_message(target_chat, caption or "(Photo missing)")

        elif ctype == 'video':
            if hasattr(message, 'video') and message.video:
                bot.send_video(target_chat, message.video.file_id, caption=caption, caption_entities=caption_entities)
            else:
                bot.send_message(target_chat, caption or "(Video content missing)")

        elif ctype == 'document':
            if hasattr(message, 'document') and message.document:
                bot.send_document(target_chat, message.document.file_id, caption=caption, caption_entities=caption_entities)
            else:
                bot.send_message(target_chat, caption or "(Document missing)")

        elif ctype == 'audio':
            if hasattr(message, 'audio') and message.audio:
                bot.send_audio(target_chat, message.audio.file_id, caption=caption, caption_entities=caption_entities)
            else:
                bot.send_message(target_chat, caption or "(Audio missing)")

        elif ctype == 'voice':
            if hasattr(message, 'voice') and message.voice:
                bot.send_voice(target_chat, message.voice.file_id, caption=caption)
            else:
                bot.send_message(target_chat, caption or "(Voice message missing)")

        elif ctype == 'animation':
            if hasattr(message, 'animation') and message.animation:
                bot.send_animation(target_chat, message.animation.file_id, caption=caption, caption_entities=caption_entities)
            else:
                bot.send_message(target_chat, caption or "(Animation missing)")

        elif ctype == 'sticker':
            if hasattr(message, 'sticker') and message.sticker:
                bot.send_sticker(target_chat, message.sticker.file_id)
            else:
                bot.send_message(target_chat, "(Sticker missing)")

        elif ctype == 'video_note':
            if hasattr(message, 'video_note') and message.video_note:
                bot.send_video_note(target_chat, message.video_note.file_id)
            else:
                bot.send_message(target_chat, "(Video note missing)")

        elif ctype == 'poll':
            if hasattr(message, 'poll') and message.poll:
                question = message.poll.question
                options = [opt.text for opt in message.poll.options]
                bot.send_poll(target_chat, question, options)
            else:
                bot.send_message(target_chat, "(Poll content missing)")

        elif ctype == 'location':
            if hasattr(message, 'location') and message.location:
                bot.send_location(target_chat, message.location.latitude, message.location.longitude)
            else:
                bot.send_message(target_chat, "(Location data missing)")

        elif ctype == 'contact':
            if hasattr(message, 'contact') and message.contact:
                bot.send_contact(target_chat, message.contact.phone_number, message.contact.first_name)
            else:
                bot.send_message(target_chat, "(Contact data missing)")

        else:
            print(f"Unsupported type: {ctype}")
            # Try to send as text if possible
            if hasattr(message, 'text') and message.text:
                bot.send_message(target_chat, f"[{ctype}] {message.text}")
            else:
                bot.send_message(target_chat, f"Unsupported message type: {ctype}")

    except Exception as e:
        print(f"Failed to send {ctype} to {target_chat}: {e}")
        # Try to send error message to debug
        try:
            bot.send_message(target_chat, f"Failed to mirror message type: {ctype}")
        except:
            pass

# ───────────────────────────────
# Mirror messages between added channels
# ───────────────────────────────
@bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'animation', 'sticker', 'video_note', 'poll', 'location', 'contact'])
def mirror_message(message):
    source_chat = message.chat.id
    if source_chat in channels:
        print(f"Mirroring {message.content_type} from {source_chat} to {len(channels)-1} channels")
        for target_chat in channels:
            if target_chat != source_chat:
                send_to_channel(target_chat, message)

# ───────────────────────────────
# Handle media groups (albums)
# ───────────────────────────────
@bot.channel_post_handler(content_types=['media_group'])
def handle_media_group(messages):
    # This will be called for each message in the media group
    # You might want to implement special handling for albums
    print(f"Media group detected with {len(messages)} items")
    # For now, let's mirror each message individually
    for message in messages:
        mirror_message(message)

# ───────────────────────────────
print("Mirror bot running...")
bot.polling(none_stop=True)