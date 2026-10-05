
# ==========================================
# 1. CREDENTIALS & API KEYS CONFIGURATION
# ==========================================
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import urllib.request
import json
import sqlite3
import time
import os

# Yahan apni asal keys direct likh dein (Termux ya Local chalane ke liye)
TELEGRAM_TOKEN = "APNA_TELEGRAM_BOT_TOKEN_YAHAN_LIKHEIN"
GEMINI_API_KEY = "APNI_GEMINI_API_KEY_YAHAN_LIKHEIN"
WEATHER_API_KEY = "APNI_WEATHER_API_KEY_YAHAN_LIKHEIN"
NEWS_API_KEY = "APNI_NEWS_API_KEY_YAHAN_LIKHEIN"

ADMIN_CHAT_ID = 123456789  

# ==========================================
# 2. AGENT RULES & SYSTEM PROMPT (ALL LANGUAGES SUPPORTED)
# ==========================================
SYSTEM_PROMPT = """
You are Ateeq's Ultra Pro Max AI Companion, a deeply empathetic, friendly, emoji-rich, authentic, and highly professional assistant.
Your core rules:
1. Communicate with warmth, politeness, wisdom, and absolute respect using lovely emojis ✨.
2. Support ALL languages fluently (Urdu, Hindi, Arabic, English, Spanish, French, Chinese, and any language the user speaks). Always reply in the exact language the user writes to you in!
3. Provide accurate, well-researched, and detailed answers with references where applicable.
4. Maintain high ethical standards at all times.
"""

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

# ==========================================
# 3. DATABASE SETUP (SQLite Persistent Memory)
# ==========================================
DB_FILE = "bot_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INTEGER,
            role TEXT,
            content TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_message(chat_id, role, content):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)', (chat_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(chat_id, limit=6):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM chat_history WHERE chat_id = ? ORDER BY rowid DESC LIMIT ?', (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for role, content in reversed(rows):
        history.append({"role": role, "parts": [{"text": content}]})
    return history

# ==========================================
# 4. LIVE WEATHER & NEWS FUNCTIONS
# ==========================================
def get_weather(city):
    if not WEATHER_API_KEY or WEATHER_API_KEY == "APNI_WEATHER_API_KEY_YAHAN_LIKHEIN":
        return "Weather API key is not configured yet. 🌦"
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            humidity = data['main']['humidity']
            return f"🌤 Weather in {city.capitalize()}:\n🌡 Temperature: {temp}°C\n☁ Condition: {desc.capitalize()}\n💧 Humidity: {humidity}%"
    except Exception as e:
        return f"Could not fetch weather for {city}. Please check the city name! 🌍"

def get_news():
    if not NEWS_API_KEY or NEWS_API_KEY == "APNI_NEWS_API_KEY_YAHAN_LIKHEIN":
        return "News API key is not configured yet. 📰"
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}&pageSize=5"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            articles = data.get('articles', [])
            if not articles:
                return "No top headlines found right now. 📰"
            news_text = "📰 *Top World News Headlines:*\n\n"
            for i, art in enumerate(articles, 1):
                news_text += f"{i}. *{art['title']}*\n{art.get('url', '')}\n\n"
            return news_text
    except Exception as e:
        return "Could not fetch latest news at the moment. 🌐"

print("=====================================================")
print("🚀 Telegram Ultra Pro Max AI Bot (All Languages) Started!")
print("=====================================================")

# ==========================================
# 5. COMMAND HANDLERS (/start, /help, /weather, /news)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    username = message.from_user.username or "User"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (chat_id, username, is_vip) VALUES (?, ?, 0)', (chat_id, username))
    conn.commit()
    conn.close()
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌤 Check Weather", callback_data="btn_weather"), InlineKeyboardButton("📰 Top News", callback_data="btn_news"))
    markup.row(InlineKeyboardButton("🤖 AI Help & Info", callback_data="btn_help"))

    welcome_text = (
        f"Hello *{username}*! ✨🌍\n\n"
        "Welcome to **Ateeq's Ultra Pro Max AI Companion**. I can speak **ALL LANGUAGES** (Urdu, Hindi, Arabic, English, etc.)! "
        "Ask me anything, check live weather using `/weather [city]`, read top news using `/news`, send photos/PDFs for analysis, or chat freely! 🚀\n\n"
        "Choose an option below or type /help:"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "🤖 *Ateeq AI Bot Full Features Menu (All Languages Supported)*\n\n"
        "• *Multilingual Chat*: Talk in Urdu, Hindi, English, Arabic or any language you prefer with lovely emojis & deep empathy 🌐\n"
        "• `/weather [city]` - Get real-time live weather updates 🌤\n"
        "• `/news` - Get top world headlines 📰\n"
        "• *Document & Image Analysis*: Send any photo, screenshot, or PDF document for instant AI review 📂\n"
        "• *Voice/Audio Support*: Send voice notes for smart processing 🎙\n\n"
        "Commands:\n"
        "/start - Start the bot with interactive buttons ✨\n"
        "/help - View this full features menu 🤖\n"
        "/broadcast - Send an announcement to all users (Admin Only) 📢"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['weather'])
def handle_weather(message):
    args = message.text.replace('/weather', '').strip()
    if not args:
        bot.reply_to(message, "Please specify a city name! Example: `/weather Lahore` 🌤", parse_mode='Markdown')
        return
    weather_info = get_weather(args)
    bot.reply_to(message, weather_info)

@bot.message_handler(commands=['news'])
def handle_news(message):
    news_info = get_news()
    bot.reply_to(message, news_info, parse_mode='Markdown')

# ==========================================
# 6. INLINE BUTTON CALLBACK HANDLER
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "btn_weather":
        bot.answer_callback_query(call.id, "Please type /weather [cityname], e.g., /weather Karachi 🌤")
        bot.send_message(call.message.chat.id, "Please type your city name like this: `/weather London` 🌍", parse_mode='Markdown')
    elif call.data == "btn_news":
        bot.answer_callback_query(call.id, "Fetching latest headlines... 📰")
        news_info = get_news()
        bot.send_message(call.message.chat.id, news_info, parse_mode='Markdown')
    elif call.data == "btn_help":
        bot.answer_callback_query(call.id, "Opening help menu... 🤖")
        send_help(call.message)

# ==========================================
# 7. ADMIN BROADCAST COMMAND
# ==========================================
@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only! 🛑")
        return
        
    text_to_broadcast = message.text.replace('/broadcast', '').strip()
    if not text_to_broadcast:
        bot.reply_to(message, "Please provide a message to broadcast! Example: `/broadcast Hello everyone!` 📢")
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    success_count = 0
    for (chat_id,) in users:
        try:
            bot.send_message(chat_id, f"📢 *Announcement from Admin*\n\n{text_to_broadcast}", parse_mode='Markdown')
            success_count += 1
        except Exception:
            pass
            
    bot.reply_to(message, f"Broadcast completed successfully! Sent to {success_count} users. 🎉")

# ==========================================
# 8. MAIN MESSAGE & MULTIMEDIA HANDLER
# ==========================================
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'document', 'voice', 'audio'])
def handle_incoming(message):
    chat_id = message.chat.id
    
    if message.content_type == 'photo':
        user_text = message.caption or "Please analyze this image in detail and provide insights with lovely explanations. 📸"
    elif message.content_type == 'document':
        user_text = message.caption or f"Please review and summarize this document file: {message.document.file_name} 📂"
    elif message.content_type in ['voice', 'audio']:
        user_text = "User sent a voice message. Acknowledge politely with warm empathy in their language and ask how you can assist them further. 🎙"
    else:
        user_text = message.text or "Hello! ✨"
    
    wait_msg = bot.reply_to(message, "Thinking... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    save_message(chat_id, "user", user_text)
    history = get_chat_history(chat_id, limit=6)
    
    data = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": history
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            reply_text = result['candidates'][0]['content']['parts'][0]['text']
            
            save_message(chat_id, "model", reply_text)
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=reply_text)
            
    except urllib.error.HTTPError as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text="Apologies, the server is currently busy. Please try again in a moment! 🔄")
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"An error occurred: {e} ⚠️")

if __name__ == "__main__":
    while True:
        try:
            print("Connecting to Telegram servers...")
            bot.polling(none_stop=True, interval=3, timeout=20)
        except Exception as e:
            print(f"Network connection warning: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
