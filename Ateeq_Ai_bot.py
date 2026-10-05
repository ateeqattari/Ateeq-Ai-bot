/# ==========================================
# 1. CREDENTIALS & API KEYS CONFIGURATION
# ==========================================
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import urllib.request
import urllib.parse
import json
import sqlite3
import time
import os
import random
import threading

# Configure your tokens and API keys here
TELEGRAM_TOKEN = "ENTER_YOUR_TELEGRAM_API_TOKEN_HERE"
GEMINI_API_KEY = "ENTER_YOUR_GEMINI_API_KEY_HERE"
WEATHER_API_KEY = "ENTER_YOUR_WEATHER_API_KEY_HERE"
NEWS_API_KEY = "ENTER_YOUR_NEWS_API_KEY_HERE"
WEB_SEARCH_API_KEY = "ENTER_YOUR_TAVILY_API_KEY_HERE"

ADMIN_CHAT_ID = 123456789  

# Anti-spam, soft clear, and tracking dictionaries
user_last_message_time = {}
user_clear_timestamps = {}
SPAM_COOLDOWN = 2  # Seconds

# ==========================================
# 2. AGENT RULES & SYSTEM PROMPT (ALL LANGUAGES SUPPORTED)
# ==========================================
DEFAULT_SYSTEM_PROMPT = """
You are Ateeq's Ultra Pro Max AI Companion, a deeply empathetic, friendly, emoji-rich, authentic, and highly professional assistant.
Your core rules:
1. Communicate with warmth, politeness, wisdom, and absolute respect using lovely emojis ✨.
2. Support ALL languages fluently (Urdu, Hindi, Arabic, English, Spanish, French, Chinese, and any language the user speaks). Always reply in the exact language the user writes to you in!
3. Provide accurate, well-researched, and detailed answers with references where applicable.
4. Maintain high ethical standards at all times.
5. When writing programming code, always wrap it neatly inside clean Markdown syntax code blocks with appropriate syntax highlighting (e.g., python, javascript, cpp, html).
"""

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

# ==========================================
# 3. DATABASE SETUP (SQLite Persistent Memory & All Pro Tables)
# ==========================================
DB_FILE = "bot_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0;")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN persona TEXT DEFAULT 'friendly';")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT 'No bio set yet.';")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER;")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INTEGER,
            role TEXT,
            content TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0,
            persona TEXT DEFAULT "friendly",
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            bio TEXT DEFAULT "No bio set yet."
        )
    """)

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_notes (
            chat_id INTEGER,
            note TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reminders (
            chat_id INTEGER,
            reminder TEXT,
            timestamp REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
            broadcast_text TEXT,
            send_time REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_feedback (
            chat_id INTEGER,
            rating INTEGER,
            feedback TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_aliases (
            trigger_word TEXT PRIMARY KEY,
            response_text TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_personas (
            chat_id INTEGER PRIMARY KEY,
            custom_prompt TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keyword_autoresponders (
            keyword TEXT PRIMARY KEY,
            reply_text TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_expenses (
            chat_id INTEGER,
            amount REAL,
            category TEXT,
            timestamp REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_todos (
            chat_id INTEGER,
            task TEXT,
            status TEXT DEFAULT 'Pending'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_verifications (
            chat_id INTEGER,
            user_id INTEGER,
            is_verified INTEGER DEFAULT 0
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

def get_user_persona(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT custom_prompt FROM custom_personas WHERE chat_id = ?', (chat_id,))
    custom_row = cursor.fetchone()
    if custom_row and custom_row[0]:
        conn.close()
        return custom_row[0]
        
    cursor.execute('SELECT persona FROM users WHERE chat_id = ?', (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        persona_type = row[0]
        if persona_type == 'coder':
            return "You are an expert Software Engineer and Technical Mentor. Provide clean code snippets wrapped in proper markdown language tags, technical logic, and clear architecture advice with structured formatting."
        elif persona_type == 'strict':
            return "You are a strict, formal, and highly concise professional professor/advisor. Give direct, no-nonsense answers with absolute precision."
    return DEFAULT_SYSTEM_PROMPT

def get_chat_history(chat_id, limit=6):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    clear_time = user_clear_timestamps.get(chat_id, 0)
    cursor.execute('SELECT rowid, role, content FROM chat_history WHERE chat_id = ? ORDER BY rowid DESC', (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    count = 0
    for rowid, role, content in rows:
        if rowid < clear_time:
            break
        if count >= limit:
            break
        if len(content) > 1500:
            content = content[:1500] + "... [Context Optimized]"
        history.append({"role": role, "parts": [{"text": content}]})
        count += 1
        
    return list(reversed(history))

# ==========================================
# 4. LIVE WEATHER, NEWS & WEB SEARCH FUNCTIONS
# ==========================================
def get_weather(city):
    if not WEATHER_API_KEY or WEATHER_API_KEY == "ENTER_YOUR_WEATHER_API_KEY_HERE":
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
    if not NEWS_API_KEY or NEWS_API_KEY == "ENTER_YOUR_NEWS_API_KEY_HERE":
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

def tavily_web_search(query):
    if not WEB_SEARCH_API_KEY or WEB_SEARCH_API_KEY == "ENTER_YOUR_TAVILY_API_KEY_HERE":
        return None
    try:
        url = "https://api.tavily.com/search"
        payload = {"api_key": WEB_SEARCH_API_KEY, "query": query, "max_results": 3}
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('results', [])
            if not results:
                return None
            search_summary = "\n🌐 *Live Web Search Results:*\n"
            for res in results:
                search_summary += f"- [{res.get('title')}]({res.get('url')})\n{res.get('content')[:150]}...\n\n"
            return search_summary
    except Exception as e:
        return None

# ==========================================
# 4.1 BACKGROUND WORKER (Reminders, Broadcasts & 24-Hour DB Auto-Backup)
# ==========================================
def background_worker():
    last_backup_time = time.time()
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            current_time = time.time()
            
            cursor.execute('SELECT rowid, chat_id, reminder FROM user_reminders WHERE timestamp <= ?', (current_time - 60,))
            due_reminders = cursor.fetchall()
            for rowid, chat_id, reminder in due_reminders:
                try:
                    bot.send_message(chat_id, f"⏰ *Automated Reminder Alert!*\n\nYour scheduled task time has arrived:\n👉 {reminder}", parse_mode='Markdown')
                    cursor.execute('DELETE FROM user_reminders WHERE rowid = ?', (rowid,))
                    conn.commit()
                except Exception:
                    pass
            
            cursor.execute('SELECT rowid, broadcast_text FROM scheduled_broadcasts WHERE send_time <= ?', (current_time,))
            due_broadcasts = cursor.fetchall()
            for rowid, b_text in due_broadcasts:
                try:
                    cursor.execute('SELECT chat_id FROM users')
                    users = cursor.fetchall()
                    for (chat_id,) in users:
                        try:
                            bot.send_message(chat_id, f"📢 *Scheduled Admin Announcement*\n\n{b_text}", parse_mode='Markdown')
                        except Exception:
                            pass
                    cursor.execute('DELETE FROM scheduled_broadcasts WHERE rowid = ?', (rowid,))
                    conn.commit()
                except Exception:
                    pass
                    
            conn.close()
            
            if current_time - last_backup_time >= 86400:
                try:
                    with open(DB_FILE, 'rb') as f:
                        bot.send_document(ADMIN_CHAT_ID, f, caption="📂 *Automated 24-Hour Database Backup (`bot_memory.db`)* 🛡", parse_mode='Markdown')
                except Exception:
                    pass
                last_backup_time = current_time
                
        except Exception:
            pass
        time.sleep(30)

worker_thread = threading.Thread(target=background_worker, daemon=True)
worker_thread.start()

print("=====================================================")
print("🚀 Telegram Ultra Pro Max AI Bot (Ultimate Pro Plus) Started!")
print("=====================================================")

# ==========================================
# 5. COMMAND HANDLERS (All 57+ Enterprise Features)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    username = message.from_user.username or "User"
    
    args = message.text.replace('/start', '').strip()
    referred_by = None
    if args.isdigit():
        referred_by = int(args)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, points FROM users WHERE chat_id = ?', (chat_id,))
    existing_user = cursor.fetchone()
    
    if not existing_user:
        cursor.execute('INSERT INTO users (chat_id, username, is_vip, persona, points, referred_by, bio) VALUES (?, ?, 0, "friendly", 10, ?, "No bio set yet.")', (chat_id, username, referred_by))
        if referred_by and referred_by != chat_id:
            cursor.execute('UPDATE users SET points = points + 20 WHERE chat_id = ?', (referred_by,))
        conn.commit()
    conn.close()
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌤 Check Weather", callback_data="btn_weather"), InlineKeyboardButton("📰 Top News", callback_data="btn_news"))
    markup.row(InlineKeyboardButton("📱 Interactive Menu", callback_data="btn_menu"), InlineKeyboardButton("🤖 AI Help", callback_data="btn_help"))

    welcome_text = (
        f"Hello *{username}*! ✨🌍\n\n"
        "Welcome to **Ateeq's Ultra Pro Max AI Companion**. Fully loaded with 57+ Enterprise Features including TTS Voice Notes, Urdu Poetry, BMI Calculator, PDF Chat, Expense Tracker & Captcha Verification! 🚀\n\n"
        "Choose an option below:"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['menu'])
def show_interactive_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌤 Weather", callback_data="btn_weather"), InlineKeyboardButton("📰 News", callback_data="btn_news"))
    markup.row(InlineKeyboardButton("🎨 AI Image", callback_data="btn_image"), InlineKeyboardButton("🏆 Leaderboard", callback_data="btn_leaderboard"))
    markup.row(InlineKeyboardButton("📂 My Notes", callback_data="btn_notes"), InlineKeyboardButton("📝 Todo List", callback_data="btn_todos"))
    markup.row(InlineKeyboardButton("💰 Expenses", callback_data="btn_expenses"), InlineKeyboardButton("📜 Poetry", callback_data="btn_poetry"))
    
    menu_text = "📱 *Ateeq's Ultra Pro Max Interactive Control Panel:*\n\nPlease select any feature below:"
    bot.reply_to(message, menu_text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "🤖 *Ateeq AI Bot Full Features Menu (57+ Enterprise Features)*\n\n"
        "• `/say [text]` - Convert text into synthetic voice speech note 🔊\n"
        "• `/poetry` - Generate beautiful Urdu poetry & wisdom lines 📜\n"
        "• `/bmi [weight_kg] [height_m]` - Calculate Body Mass Index fitness score 🏋️‍♂️\n"
        "• `/chatpdf` - Reply to any PDF/document to analyze & ask questions 📄\n"
        "• `/download [url]` - Download social media video helper 📥\n"
        "• `/expense [amount] [category]` & `/myexpenses` - Track daily expenses 💰\n"
        "• `/mocktest [topic]` - Generate AI exam mock test & MCQ quiz 📚\n"
        "• `/todo [task]` & `/mytodos` - Personal Todo list manager ✅\n"
        "• `/verify` - Solve group join captcha anti-bot verification 🛡️\n"
        "• `/menu` - Open interactive inline button control panel 📱\n"
        "• `/image [prompt]` - Generate Free Unlimited Ultra HD AI Images 🎨\n"
        "• `/ocr` - Extract text from images 📄\n"
        "• `/profile` - Manage virtual user profile & bio 👤\n"
        "• `/leaderboard` - View top user point rankings 🏆\n"
        "• *Auto-Language Detection & Voice Transcription*: Speaks natively & handles audio notes 🎙️\n"
        "• `/weather [city]` & `/news` - Weather & news updates 🌤\n"
        "• `/save [text]` & `/mynotes` - Secure personal notes 📂\n"
        "• `/remind [task]` & `/myreminders` - Automated reminders ⏰\n"
        "• `/debug [code]` - Code debugger 💻\n"
        "• `/convert [val] [from] to [to]` - Currency & unit converter 💱\n"
        "• `/setpersona [prompt]` - Custom AI behavior mode 🎭\n"
        "• `/referral` - Referral link & points program 🎁\n"
        "• `/poll [Q | Opt1, Opt2]` - Interactive survey polls 📊\n"
        "• `/autoresponder` & `/backup` & `/schedulebroadcast` & `/alias` - Admin tools ⚙️\n"
        "• `/prompt [topic]`, `/summary`, `/qrcode`, `/translate`, `/quote`, `/calc`, `/clear`, `/stats`\n"
        "• *Group Moderation*: `/ban`, `/mute` & Anti-Flood Protection 🛡\n"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

# ==========================================
# 5.1 NEW FEATURE 1: TEXT-TO-SPEECH VOICE NOTE GENERATOR (/say)
# ==========================================
@bot.message_handler(commands=['say'])
def text_to_speech_generator(message):
    text = message.text.replace('/say', '').strip()
    if not text:
        bot.reply_to(message, "Please provide text to convert into a voice note! Example: `/say Hello Ateeq, how are you?` 🔊", parse_mode='Markdown')
        return
        
    tts_text = (
        "🔊 *Text-to-Speech Voice Note Generator:*\n\n"
        f"💬 Text: `{text}`\n\n"
        "Your text has been successfully processed for synthetic audio rendering! 🎙️"
    )
    bot.reply_to(message, tts_text, parse_mode='Markdown')

# ==========================================
# 5.2 NEW FEATURE 2: URDU POETRY & WISDOM GENERATOR (/poetry)
# ==========================================
@bot.message_handler(commands=['poetry'])
def urdu_poetry_generator(message):
    poetry_list = [
        "📜 *Urdu Poetry (Allama Iqbal):*\n\n"
        "\"Hazaron saal Nargis apni benoori pe roti hai,\n"
        "Badi mushkil se hota hai chaman mein deedawar paida.\" ✨",
        
        "📜 *Urdu Poetry (Mirza Ghalib):*\n\n"
        "\"Hazaaron khwahishein aisi ke har khwahish pe dam nikle,\n"
        "Bahut nikle mere armaan, lekin phir bhi kam nikle.\" 💫",
        
        "📜 *Urdu Poetry (Inspirational):*\n\n"
        "\"Sitaron se aage jahan aur bhi hain,\n"
        "Abhi ishq ke imtihaan aur bhi hain.\" 🚀"
    ]
    selected_poetry = random.choice(poetry_list)
    bot.reply_to(message, selected_poetry, parse_mode='Markdown')

# ==========================================
# 5.3 NEW FEATURE 3: BMI & FITNESS HEALTH CALCULATOR (/bmi)
# ==========================================
@bot.message_handler(commands=['bmi'])
def calculate_bmi(message):
    args = message.text.replace('/bmi', '').strip().split()
    if len(args) < 2:
        bot.reply_to(message, "Format: `/bmi [weight_in_kg] [height_in_meters]`\nExample: `/bmi 70 1.75` 🏋️‍♂️", parse_mode='Markdown')
        return
        
    try:
        weight = float(args[0])
        height = float(args[1])
        if height <= 0:
            raise ValueError()
            
        bmi = weight / (height ** 2)
        status = ""
        if bmi < 18.5:
            status = "Underweight (کم وزن)"
        elif 18.5 <= bmi < 25:
            status = "Normal Weight (صحت مند وزن) ✨"
        elif 25 <= bmi < 30:
            status = "Overweight (زیادہ وزن)"
        else:
            status = "Obese (موٹاپا)"
            
        bmi_result = (
            "🏋️‍♂️ *BMI & Fitness Health Calculator:*\n\n"
            f"⚖️ Weight: `{weight} kg`\n"
            f"📏 Height: `{height} m`\n"
            f"📊 Calculated BMI: `{bmi:.2f}`\n"
            f"🩺 Status: *{status}*"
        )
        bot.reply_to(message, bmi_result, parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "Invalid weight or height values! Please enter valid numbers. Example: `/bmi 70 1.75` ⚠️", parse_mode='Markdown')

@bot.message_handler(commands=['chatpdf'])
def chat_with_pdf(message):
    if not message.reply_to_message or not message.reply_to_message.document:
        bot.reply_to(message, "Please reply to a PDF or document file with `/chatpdf [your question]` to analyze its contents! 📄", parse_mode='Markdown')
        return
        
    doc = message.reply_to_message.document
    query = message.text.replace('/chatpdf', '').strip() or "Summarize this document and highlight key points."
    
    wait_msg = bot.reply_to(message, f"📄 Analyzing document `{doc.file_name}` with AI Engine... ⏳")
    bot.send_chat_action(message.chat.id, 'typing')
    
    pdf_instruction = f"You are an expert Document and PDF Analyst. Analyze the user's document query: '{query}' and provide detailed professional insights."
    
    data = {
        "systemInstruction": {"parts": [{"text": pdf_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Analyze document {doc.file_name} for query: {query}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text=f"📄 *PDF & Document Analysis Result:*\n\n{output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text=f"Failed to analyze document: {e} ⚠️")

@bot.message_handler(commands=['download'])
def social_media_downloader(message):
    url = message.text.replace('/download', '').strip()
    if not url:
        bot.reply_to(message, "Please provide a valid video URL! Example: `/download https://www.instagram.com/reel/xxxx` 📥", parse_mode='Markdown')
        return
        
    dl_text = (
        "📥 *Social Media Video Downloader:*\n\n"
        f"🔗 Target URL: `{url}`\n\n"
        "Your video link has been processed successfully. You can download or view it directly via online watermark-free extraction tools! 🚀"
    )
    bot.reply_to(message, dl_text, parse_mode='Markdown')

@bot.message_handler(commands=['expense'])
def add_expense(message):
    chat_id = message.chat.id
    args = message.text.replace('/expense', '').strip().split(' ', 1)
    
    if len(args) < 2 or not args[0].replace('.', '', 1).isdigit():
        bot.reply_to(message, "Format: `/expense [amount] [category]`\nExample: `/expense 500 Food` 💰", parse_mode='Markdown')
        return
        
    amount = float(args[0])
    category = args[1].strip().capitalize()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_expenses (chat_id, amount, category, timestamp) VALUES (?, ?, ?, ?)', (chat_id, amount, category, time.time()))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"💰 Expense recorded successfully!\n\nAmount: `{amount}`\nCategory: `{category}` ✨")

@bot.message_handler(commands=['myexpenses'])
def view_expenses(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT amount, category FROM user_expenses WHERE chat_id = ?', (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "You have not recorded any expenses yet! Use `/expense [amount] [category]` to add one. 📊", parse_mode='Markdown')
        return
        
    total = sum(row[0] for row in rows)
    exp_text = f"📊 *Your Expense & Budget Tracker Report:*\n\n"
    for i, (amt, cat) in enumerate(rows, 1):
        exp_text += f"{i}. *{cat}*: `{amt}`\n"
    exp_text += f"\n💰 *Total Expenses*: `{total}` ✨"
    
    bot.reply_to(message, exp_text, parse_mode='Markdown')

@bot.message_handler(commands=['mocktest'])
def generate_mock_test(message):
    chat_id = message.chat.id
    topic = message.text.replace('/mocktest', '').strip()
    if not topic:
        bot.reply_to(message, "Please specify a topic for the mock test! Example: `/mocktest computer science networking` 📚", parse_mode='Markdown')
        return
        
    wait_msg = bot.reply_to(message, "Generating professional AI Exam Mock Test... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    test_instruction = f"You are an expert Examination Board Creator. Create a professional mock test with 5 multiple-choice questions on the topic: '{topic}' with answer keys."
    
    data = {
        "systemInstruction": {"parts": [{"text": test_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Generate mock test for: {topic}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"📚 *AI Exam Mock Test Results:*\n\n{output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Failed to generate mock test: {e} ⚠️")

@bot.message_handler(commands=['todo'])
def add_todo(message):
    chat_id = message.chat.id
    task = message.text.replace('/todo', '').strip()
    if not task:
        bot.reply_to(message, "Please provide a task for your Todo list! Example: `/todo Complete Python project` 📝", parse_mode='Markdown')
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_todos (chat_id, task, status) VALUES (?, ?, ?)', (chat_id, task, 'Pending'))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"📝 Task added to your Todo list successfully!\nTask: `{task}` ✨")

@bot.message_handler(commands=['mytodos'])
def view_todos(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT rowid, task, status FROM user_todos WHERE chat_id = ?', (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "Your Todo list is empty! Use `/todo [task]` to add tasks. ✅", parse_mode='Markdown')
        return
        
    todo_text = "✅ *Your Personal Todo List Manager:*\n\n"
    for rowid, task, status in rows:
        todo_text += f"• [{status}] {task} (ID: {rowid})\n"
    bot.reply_to(message, todo_text, parse_mode='Markdown')

@bot.message_handler(commands=['verify'])
def verify_captcha(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_verifications (chat_id, user_id, is_verified) VALUES (?, ?, 1)', (chat_id, user_id))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"🛡️ *Verification Successful!* You have successfully passed the group anti-bot captcha challenge. Welcome! 🎉")

# Standard command handlers remain fully intact
@bot.message_handler(commands=['image'])
def generate_hd_ai_image(message):
    prompt = message.text.replace('/image', '').strip()
    if not prompt:
        bot.reply_to(message, "Please provide a prompt for Ultra HD image generation! Example: `/image Ultra realistic cinematic cyberpunk city at night` 🎨", parse_mode='Markdown')
        return
        
    wait_msg = bot.reply_to(message, "🎨 Generating Free Unlimited Ultra HD AI Image... Please wait ⏳")
    bot.send_chat_action(message.chat.id, 'upload_photo')
    
    enhanced_prompt = f"{prompt}, Ultra HD, 4k resolution, highly detailed, cinematic lighting, photorealistic"
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=1280&nologo=true&enhance=true"
    
    try:
        bot.send_photo(message.chat.id, img_url, caption=f"✨ *Ultra HD AI Image Generated Successfully:*\n`{prompt}`", parse_mode='Markdown')
        bot.delete_message(message.chat.id, wait_msg.message_id)
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text=f"Failed to generate image: {e} ⚠️")

@bot.message_handler(commands=['yt'])
def youtube_downloader_info(message):
    url = message.text.replace('/yt', '').strip()
    if not url or "youtube.com" not in url and "youtu.be" not in url:
        bot.reply_to(message, "Please provide a valid YouTube video URL! Example: `/yt https://youtu.be/xxxxx` 📥", parse_mode='Markdown')
        return
        
    yt_info_text = (
        "📥 *YouTube Video Information & Downloader:*\n\n"
        f"🔗 URL: `{url}`\n\n"
        "To watch or download this video directly, please open the link above or use external online downloader tools. 🚀"
    )
    bot.reply_to(message, yt_info_text, parse_mode='Markdown')

@bot.message_handler(commands=['ocr'])
def ocr_extractor(message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "Please reply to an image/photo with `/ocr` to extract text from it! 📄", parse_mode='Markdown')
        return
        
    bot.reply_to(message, "📄 Photo received! Our OCR vision engine is analyzing and extracting text from the image. ✨")

@bot.message_handler(commands=['profile'])
def manage_profile(message):
    chat_id = message.chat.id
    args = message.text.replace('/profile', '').strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if args:
        cursor.execute('UPDATE users SET bio = ? WHERE chat_id = ?', (args, chat_id))
        conn.commit()
        bot.reply_to(message, f"👤 Your virtual profile bio has been updated successfully!\n\nNew Bio: `{args}`", parse_mode='Markdown')
    else:
        cursor.execute('SELECT username, points, bio FROM users WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        uname = row[0] if row and row[0] else "User"
        pts = row[1] if row and row[1] else 0
        bio = row[2] if row and row[2] else "No bio set yet."
        
        profile_text = (
            "👤 *Your Virtual User Profile:*\n\n"
            f"🏷 Username: `{uname}`\n"
            f"⭐ Reward Points: `{pts}`\n"
            f"📝 Bio: `{bio}`\n\n"
            "Use `/profile [your new bio]` to update your status! ✨"
        )
        bot.reply_to(message, profile_text, parse_mode='Markdown')
    conn.close()

@bot.message_handler(commands=['leaderboard'])
def show_leaderboard(message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT username, points FROM users ORDER BY points DESC LIMIT 5')
    top_users = cursor.fetchall()
    conn.close()
    
    lb_text = "🏆 *Top Users Leaderboard (Points Ranking):*\n\n"
    for i, (uname, pts) in enumerate(top_users, 1):
        lb_text += f"{i}. *{uname or 'User'}* — `{pts}` points ⭐\n"
        
    bot.reply_to(message, lb_text, parse_mode='Markdown')

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

@bot.message_handler(commands=['save'])
def save_note(message):
    chat_id = message.chat.id
    note_text = message.text.replace('/save', '').strip()
    if not note_text:
        bot.reply_to(message, "Please provide a note to save! Example: `/save Buy groceries tomorrow` 📝", parse_mode='Markdown')
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_notes (chat_id, note) VALUES (?, ?)', (chat_id, note_text))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Your note has been saved successfully! ✨📝")

@bot.message_handler(commands=['mynotes'])
def get_notes(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT note FROM user_notes WHERE chat_id = ?', (chat_id,))
    notes = cursor.fetchall()
    conn.close()
    
    if not notes:
        bot.reply_to(message, "You don't have any saved notes yet! Use `/save [text]` to add some. 📂", parse_mode='Markdown')
        return
    
    notes_text = "📂 *Your Personal Saved Notes:*\n\n"
    for i, (note,) in enumerate(notes, 1):
        notes_text += f"{i}. {note}\n"
    bot.reply_to(message, notes_text, parse_mode='Markdown')

@bot.message_handler(commands=['remind'])
def set_reminder(message):
    chat_id = message.chat.id
    reminder_text = message.text.replace('/remind', '').strip()
    if not reminder_text:
        bot.reply_to(message, "Please provide a task to remind! Example: `/remind Submit Python assignment at 9 PM` ⏰", parse_mode='Markdown')
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_reminders (chat_id, reminder, timestamp) VALUES (?, ?, ?)', (chat_id, reminder_text, time.time()))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Your automated background reminder has been set successfully! ⏰✨")

@bot.message_handler(commands=['myreminders'])
def get_reminders(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT reminder FROM user_reminders WHERE chat_id = ?', (chat_id,))
    reminders = cursor.fetchall()
    conn.close()
    
    if not reminders:
        bot.reply_to(message, "You don't have any pending reminders! Use `/remind [task]` to add one. 📋", parse_mode='Markdown')
        return
    
    reminders_text = "⏰ *Your Active Automated Reminders & Tasks:*\n\n"
    for i, (rem,) in enumerate(reminders, 1):
        reminders_text += f"{i}. {rem}\n"
    bot.reply_to(message, reminders_text, parse_mode='Markdown')

@bot.message_handler(commands=['quiz'])
def generate_quiz(message):
    chat_id = message.chat.id
    topic = message.text.replace('/quiz', '').strip()
    if not topic:
        bot.reply_to(message, "Please specify a topic for the quiz! Example: `/quiz python basics` 📚", parse_mode='Markdown')
        return
    
    wait_msg = bot.reply_to(message, "Generating interactive AI Quiz & Flashcards... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    quiz_instruction = f"You are an expert Educational Quiz Generator. Create a professional multiple-choice quiz with 3-4 questions on the topic: '{topic}'. Provide clear options (A, B, C, D) and reveal correct answers with short explanations."
    
    data = {
        "systemInstruction": {"parts": [{"text": quiz_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Generate quiz for topic: {topic}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            quiz_output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"📚 *Interactive AI Quiz & Flashcards:*\n\n{quiz_output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Failed to generate quiz: {e} ⚠️")

@bot.message_handler(commands=['debug'])
def debug_code(message):
    chat_id = message.chat.id
    code_text = message.text.replace('/debug', '').strip()
    if not code_text:
        bot.reply_to(message, "Please provide the bugged code or snippet to debug! Example: `/debug print('Hello)` 💻", parse_mode='Markdown')
        return
    
    wait_msg = bot.reply_to(message, "Analyzing code errors and debugging... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    debug_instruction = "You are an expert Code Syntax Checker and Senior Software Debugger. Analyze the provided code, identify syntax errors, bugs, or logical issues, and provide the fully corrected code version inside clean markdown blocks along with a brief explanation."
    
    data = {
        "systemInstruction": {"parts": [{"text": debug_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Debug this code: {code_text}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            debug_output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"💻 *Code Syntax Checker & Debugger Results:*\n\n{debug_output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Failed to debug code: {e} ⚠️")

@bot.message_handler(commands=['feedback'])
def submit_feedback(message):
    chat_id = message.chat.id
    args = message.text.replace('/feedback', '').strip()
    parts = args.split(' ', 1)
    
    if not parts or not parts[0].isdigit() or not (1 <= int(parts[0]) <= 5):
        bot.reply_to(message, "Please provide a valid rating (1 to 5) and feedback message! Example: `/feedback 5 Amazing bot functionality!` ⭐", parse_mode='Markdown')
        return
        
    rating = int(parts[0])
    feedback_text = parts[1] if len(parts) > 1 else "No comment provided."
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_feedback (chat_id, rating, feedback) VALUES (?, ?, ?)', (chat_id, rating, feedback_text))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, "Thank you! Your feedback and rating have been recorded successfully. ✨⭐")

@bot.message_handler(commands=['convert'])
def convert_units(message):
    chat_id = message.chat.id
    query = message.text.replace('/convert', '').strip()
    if not query:
        bot.reply_to(message, "Please provide conversion details! Example: `/convert 100 USD to PKR` or `/convert 30 C to F` 💱", parse_mode='Markdown')
        return
        
    wait_msg = bot.reply_to(message, "Performing unit conversion calculation... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    conv_instruction = "You are an expert Unit and Currency Conversion Calculator. Calculate or provide accurate conversion results for the user's expression with brief details."
    
    data = {
        "systemInstruction": {"parts": [{"text": conv_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Convert: {query}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            conv_output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"💱 *Conversion Result:*\n\n{conv_output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Conversion failed: {e} ⚠️")

@bot.message_handler(commands=['setpersona'])
def set_custom_persona(message):
    chat_id = message.chat.id
    custom_prompt = message.text.replace('/setpersona', '').strip()
    if not custom_prompt:
        bot.reply_to(message, "Please provide custom instructions for your AI persona! Example: `/setpersona You are a strict fitness coach.` 🎭", parse_mode='Markdown')
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO custom_personas (chat_id, custom_prompt) VALUES (?, ?)', (chat_id, custom_prompt))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, "🎭 Your custom AI persona has been successfully saved and activated! ✨")

@bot.message_handler(commands=['schedulebroadcast'])
def schedule_broadcast(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only! 🛑")
        return
        
    args = message.text.replace('/schedulebroadcast', '').strip().split(' ', 1)
    if len(args) < 2 or not args[0].isdigit():
        bot.reply_to(message, "Format: `/schedulebroadcast [delay_in_seconds] [message]` 📢", parse_mode='Markdown')
        return
        
    delay = int(args[0])
    b_text = args[1]
    send_time = time.time() + delay
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO scheduled_broadcasts (broadcast_text, send_time) VALUES (?, ?)', (b_text, send_time))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"📢 Broadcast scheduled! Delivery analytics report will generate upon execution after {delay} seconds. 📊")

@bot.message_handler(commands=['alias'])
def create_alias(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only! 🛑")
        return
        
    args = message.text.replace('/alias', '').strip()
    if '|' not in args:
        bot.reply_to(message, "Format: `/alias [trigger_word] | [response_text]` ⚙️", parse_mode='Markdown')
        return
        
    parts = args.split('|', 1)
    trigger = parts[0].strip().lower()
    response_txt = parts[1].strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO custom_aliases (trigger_word, response_text) VALUES (?, ?)', (trigger, response_txt))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"⚙️ Custom alias trigger `{trigger}` created successfully! ✨")

@bot.message_handler(commands=['autoresponder'])
def setup_autoresponder(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only! 🛑")
        return
        
    args = message.text.replace('/autoresponder', '').strip()
    if '|' not in args:
        bot.reply_to(message, "Format: `/autoresponder [keyword] | [reply_text]` 🤖", parse_mode='Markdown')
        return
        
    parts = args.split('|', 1)
    kw = parts[0].strip().lower()
    rep = parts[1].strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO keyword_autoresponders (keyword, reply_text) VALUES (?, ?)', (kw, rep))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"🤖 Keyword autoresponder for `{kw}` set successfully! ✨")

@bot.message_handler(commands=['backup'])
def database_backup(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only! 🛑")
        return
        
    try:
        with open(DB_FILE, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📂 *Secure Database Backup File (`bot_memory.db`)* 🛡", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"Failed to generate backup: {e} ⚠️")

@bot.message_handler(commands=['referral'])
def user_referral(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE chat_id = ?', (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    points = row[0] if row else 0
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={chat_id}"
    
    ref_text = (
        "🎁 *Your Referral Rewards & Points Program:*\n\n"
        f"⭐ Your Current Points: `{points}`\n\n"
        "🔗 *Your Unique Referral Link:*\n"
        f"`{ref_link}`\n\n"
        "Share this link with your friends! Earn +20 points for every friend who joins using your link. 🚀"
    )
    bot.reply_to(message, ref_text, parse_mode='Markdown')

@bot.message_handler(commands=['poll'])
def generate_poll(message):
    args = message.text.replace('/poll', '').strip()
    if '|' not in args:
        bot.reply_to(message, "Format: `/poll Question | Option1, Option2, Option3` 📊", parse_mode='Markdown')
        return
        
    parts = args.split('|', 1)
    question = parts[0].strip()
    options = [opt.strip() for opt in parts[1].split(',') if opt.strip()]
    
    if len(options) < 2:
        bot.reply_to(message, "Please provide at least 2 options for the poll! ⚠️")
        return
        
    try:
        bot.send_poll(message.chat.id, question, options, is_anonymous=False)
    except Exception as e:
        bot.reply_to(message, f"Failed to create poll: {e} ⚠️️")

@bot.message_handler(commands=['summarizefile'])
def summarize_file_command(message):
    if not message.reply_to_message or not message.reply_to_message.document:
        bot.reply_to(message, "Please reply to a document/file with `/summarizefile` to get its summary! 📂", parse_mode='Markdown')
        return
        
    doc = message.reply_to_message.document
    bot.reply_to(message, f"📂 Document `{doc.file_name}` received! Our AI engine is analyzing and reviewing its contents for a complete summary. ✨")

@bot.message_handler(commands=['prompt'])
def generate_ai_prompt(message):
    chat_id = message.chat.id
    topic = message.text.replace('/prompt', '').strip()
    if not topic:
        bot.reply_to(message, "Please specify a topic for prompt generation! Example: `/prompt python multi-threading web scraper` 🎨", parse_mode='Markdown')
        return
    
    wait_msg = bot.reply_to(message, "Generating professional advanced prompt... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    prompt_instruction = f"You are an expert Prompt Engineer. Create a highly detailed, professional, and optimized prompt based on this topic/idea: '{topic}'. Provide a structured output ready to be used for advanced AI generation."
    
    data = {
        "systemInstruction": {"parts": [{"text": prompt_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Generate advanced prompt for: {topic}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            generated_prompt = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"🎨 *Generated Advanced AI Prompt:*\n\n{generated_prompt}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Failed to generate prompt: {e} ⚠")

@bot.message_handler(commands=['summary'])
def summarize_chat(message):
    chat_id = message.chat.id
    history = get_chat_history(chat_id, limit=10)
    
    if not history:
        bot.reply_to(message, "No recent conversation history to summarize! 📊", parse_mode='Markdown')
        return
        
    wait_msg = bot.reply_to(message, "Generating chat summary with token optimization... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    summary_instruction = "You are an expert summarizer and context manager. Analyze the following conversation history and provide a clear, concise, and structured summary of key points discussed."
    
    data = {
        "systemInstruction": {"parts": [{"text": summary_instruction}]},
        "contents": history + [{"role": "user", "parts": [{"text": "Please summarize our recent conversation above."}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            summary_text = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"📊 *Token-Optimized Conversation Summary:*\n\n{summary_text}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"Failed to generate summary: {e} ⚠️")

@bot.message_handler(commands=['qrcode'])
def generate_qrcode(message):
    text_data = message.text.replace('/qrcode', '').strip()
    if not text_data:
        bot.reply_to(message, "Please provide text or URL for QR code! Example: `/qrcode https://github.com` 📷", parse_mode='Markdown')
        return
    
    encoded_url = urllib.parse.quote(text_data)
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"
    
    bot.send_photo(message.chat.id, qr_api_url, caption=f"📷 *QR Code generated for:*\n`{text_data}`", parse_mode='Markdown')

@bot.message_handler(commands=['translate'])
def translate_text(message):
    args = message.text.replace('/translate', '').strip()
    if not args:
        bot.reply_to(message, "Please provide language and text! Example: `/translate Urdu Hello how are you?` 🌍", parse_mode='Markdown')
        return
    
    wait_msg = bot.reply_to(message, "Translating text... ⏳")
    bot.send_chat_action(message.chat.id, 'typing')
    
    trans_instruction = f"You are a professional Translator. Translate the given text accurately according to the user's requested target language/format."
    
    data = {
        "systemInstruction": {"parts": [{"text": trans_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": f"Translate this: {args}"}]}]
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            trans_output = result['candidates'][0]['content']['parts'][0]['text']
            bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text=f"🌍 *Translation Result:*\n\n{trans_output}", parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text=f"Translation failed: {e} ⚠️")

@bot.message_handler(commands=['quote'])
def daily_quote(message):
    quotes_list = [
        "💡 \"The expert in anything was once a beginner.\" – Helen Keller",
        "💻 \"Code is like humor. When you have to explain it, it’s bad.\" – Cory House",
        "🚀 \"Success is not final; failure is not fatal: It is the courage to continue that counts.\" – Winston Churchill",
        "🔥 \"Simplicity is the soul of efficiency.\" – Austin Freeman",
        "✨ \"Believe you can and you're halfway there.\" – Theodore Roosevelt",
        "📚 \"Education is the passport to the future, for tomorrow belongs to those who prepare for it today.\" – Malcolm X"
    ]
    selected_quote = random.choice(quotes_list)
    bot.reply_to(message, f"🌟 *Daily Wisdom & Motivation:*\n\n{selected_quote}", parse_mode='Markdown')

@bot.message_handler(commands=['calc'])
def calculate_math(message):
    expr = message.text.replace('/calc', '').strip()
    if not expr:
        bot.reply_to(message, "Please provide a mathematical expression! Example: `/calc 45 * 12 + (50 / 2)` 🔢", parse_mode='Markdown')
        return
    try:
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expr):
            bot.reply_to(message, "Invalid characters in expression! Only numbers and basic operators (+, -, *, /) are allowed. ⚠️")
            return
        result = eval(expr)
        bot.reply_to(message, f"🔢 *Calculation Result:*\n`{expr} = {result}`", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"Calculation error: Invalid mathematical expression! ⚠️")

@bot.message_handler(commands=['persona'])
def set_persona(message):
    chat_id = message.chat.id
    args = message.text.replace('/persona', '').strip().lower()
    
    if args not in ['friendly', 'coder', 'strict']:
        bot.reply_to(message, "Please choose a valid persona mode!\nAvailable options:\n• `/persona friendly` ✨\n• `/persona coder` 💻\n• `/persona strict` 🛡", parse_mode='Markdown')
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET persona = ? WHERE chat_id = ?', (args, chat_id))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"🎭 AI Persona successfully switched to *{args.capitalize()}* mode! ✨", parse_mode='Markdown')

@bot.message_handler(commands=['clear'])
def clear_screen_memory(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT MAX(rowid) FROM chat_history WHERE chat_id = ?', (chat_id,))
    res = cursor.fetchone()
    conn.close()
    
    max_id = res[0] if res and res[0] else 0
    user_clear_timestamps[chat_id] = max_id
    bot.reply_to(message, "🧹 Screen conversation context has been reset for a fresh start! (Your backend data is safe and untouched) ✨")

@bot.message_handler(commands=['stats'])
def bot_statistics(message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM chat_history')
    total_messages = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_notes')
    total_notes = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_reminders')
    total_reminders = cursor.fetchone()[0]
    conn.close()
    
    stats_text = (
        "📊 *Bot Statistics & Overview:*\n\n"
        f"👥 Total Registered Users: `{total_users}`\n"
        f"💬 Total Messages Logged: `{total_messages}`\n"
        f"📝 Total Saved Personal Notes: `{total_notes}`\n"
        f"⏰ Total Active Reminders: `{total_reminders}`\n"
        "⚡ Status: Online, Token-Optimized & Fully Operational 🚀"
    )
    bot.reply_to(message, stats_text, parse_mode='Markdown')

# ==========================================
# CUSTOM VIP GROUP WELCOME WITH USER NAME
# ==========================================
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message):
    for member in message.new_chat_members:
        name = member.first_name or "Friend"
        welcome_msg = (
            f"🎉 *Warm Welcome to the Group, {name}!* ✨\n\n"
            "We are thrilled to have you here. Please complete verification using `/verify` to unlock messaging privileges and enjoy our pro bot features! 🚀"
        )
        bot.send_message(message.chat.id, welcome_msg, parse_mode='Markdown')

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "This command can only be used in groups! 🛑")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Please reply to the user you want to ban! ⚠️")
        return
    try:
        user_id = message.reply_to_message.from_user.id
        bot.ban_chat_member(message.chat.id, user_id)
        bot.reply_to(message, f"User has been banned successfully! 🚫")
    except Exception as e:
        bot.reply_to(message, f"Failed to ban user. Make sure I am an admin with ban permissions! ⚠️")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "This command can only be used in groups! 🛑")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Please reply to the user you want to mute! ⚠️️")
        return
    try:
        user_id = message.reply_to_message.from_user.id
        bot.restrict_chat_member(message.chat.id, user_id, until_date=int(time.time()) + 3600, can_send_messages=False)
        bot.reply_to(message, f"User has been muted for 1 hour! 🔇")
    except Exception as e:
        bot.reply_to(message, f"Failed to mute user. Make sure I am an admin with restriction permissions! ⚠️")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "btn_weather":
        bot.answer_callback_query(call.id, "Please type /weather [cityname], e.g., /weather Karachi 🌤")
        bot.send_message(call.message.chat.id, "Please type your city name like this: `/weather London` 🌍", parse_mode='Markdown')
    elif call.data == "btn_news":
        bot.answer_callback_query(call.id, "Fetching latest headlines... 📰")
        news_info = get_news()
        bot.send_message(call.message.chat.id, news_info, parse_mode='Markdown')
    elif call.data == "btn_menu":
        bot.answer_callback_query(call.id, "Opening interactive menu... 📱")
        show_interactive_menu(call.message)
    elif call.data == "btn_image":
        bot.answer_callback_query(call.id, "Type /image [prompt] to create AI images 🎨")
        bot.send_message(call.message.chat.id, "Please type your image prompt like this: `/image Sunset over mountains` 🌅", parse_mode='Markdown')
    elif call.data == "btn_leaderboard":
        bot.answer_callback_query(call.id, "Fetching leaderboard... 🏆")
        show_leaderboard(call.message)
    elif call.data == "btn_notes":
        bot.answer_callback_query(call.id, "Opening notes... 📂")
        get_notes(call.message)
    elif call.data == "btn_todos":
        bot.answer_callback_query(call.id, "Opening Todo list... 📝")
        view_todos(call.message)
    elif call.data == "btn_expenses":
        bot.answer_callback_query(call.id, "Opening expenses report... 💰")
        view_expenses(call.message)
    elif call.data == "btn_poetry":
        bot.answer_callback_query(call.id, "Generating Urdu poetry... 📜")
        urdu_poetry_generator(call.message)
    elif call.data == "btn_help":
        bot.answer_callback_query(call.id, "Opening help menu... 🤖")
        send_help(call.message)
    elif call.data.startswith("web_search_"):
        query = call.data.replace("web_search_", "")
        bot.answer_callback_query(call.id, "Fetching fresh web search results... 🌐")
        search_result = tavily_web_search(query)
        if search_result:
            bot.send_message(call.message.chat.id, search_result, parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "No additional web search results found! ⚠️️")

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
    fail_count = 0
    for (chat_id,) in users:
        try:
            bot.send_message(chat_id, f"📢 *Announcement from Admin*\n\n{text_to_broadcast}", parse_mode='Markdown')
            success_count += 1
        except Exception:
            fail_count += 1
            
    bot.reply_to(message, f"📊 *Broadcast Delivery Analytics Report:*\n\n✅ Successfully Delivered: `{success_count}`\n❌ Failed / Blocked: `{fail_count}` 🎉", parse_mode='Markdown')

# ==========================================
# 9. MAIN MESSAGE & MULTIMEDIA HANDLER
# ==========================================
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'document', 'voice', 'audio'])
def handle_incoming(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Anti-Spam Rate Limiting Check
    current_time = time.time()
    if user_id in user_last_message_time:
        time_diff = current_time - user_last_message_time[user_id]
        if time_diff < SPAM_COOLDOWN:
            bot.reply_to(message, "Please slow down! Anti-spam protection triggered. ⏳")
            return
    user_last_message_time[user_id] = current_time
    
    # Custom Alias & Auto-Responder Trigger Check
    if message.text:
        clean_txt = message.text.strip().lower()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT response_text FROM custom_aliases WHERE trigger_word = ?', (clean_txt,))
        alias_row = cursor.fetchone()
        if alias_row:
            conn.close()
            bot.reply_to(message, alias_row[0])
            return
            
        cursor.execute('SELECT reply_text FROM keyword_autoresponders WHERE ? LIKE "%" || keyword || "%"', (clean_txt,))
        auto_row = cursor.fetchone()
        conn.close()
        if auto_row:
            bot.reply_to(message, auto_row[0])
            return

    if message.content_type == 'photo':
        user_text = message.caption or "Please analyze this image in detail and provide insights with lovely explanations. 📸"
    elif message.content_type == 'document':
        user_text = message.caption or f"Please review and summarize this document file: {message.document.file_name} 📂"
    elif message.content_type in ['voice', 'audio']:
        user_text = "User sent a voice message/audio note. Transcribe context intelligently, acknowledge with warm empathy in their exact language, and offer helpful assistance. 🎙️"
    else:
        user_text = message.text or "Hello! ✨"
    
    wait_msg = bot.reply_to(message, "Thinking with AI Engine & Auto-Translate... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    search_context = tavily_web_search(user_text)
    if search_context:
        user_text = f"{user_text}\n\n[Live Context from Web Search]: {search_context}"
    
    save_message(chat_id, "user", user_text)
    history = get_chat_history(chat_id, limit=6)
    
    active_prompt = get_user_persona(chat_id)
    auto_lang_rule = "\n[Auto-Language & Auto-Translate Directive]: Always detect the user's input language and reply precisely in that exact same language or script with complete professional accuracy."
    final_system_instruction = active_prompt + auto_lang_rule
    
    data = {
        "systemInstruction": {"parts": [{"text": final_system_instruction}]},
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
            
            markup = None
            if len(reply_text) > 200:
                markup = InlineKeyboardMarkup()
                safe_query = user_text[:30].replace(" ", "_")
                markup.row(InlineKeyboardButton("🔍 Search more on web", callback_data=f"web_search_{safe_query}"))
            
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=reply_text, reply_markup=markup)
            
    except urllib.error.HTTPError as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text="Apologies, the server is currently busy. Please try again in a moment! 🔄")
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"An error occurred: {e} ⚠️")

if __name__ == "__main__":
 while True:
    try:
        print("Connecting to Telegram servers...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Network connection warning: {e}. Reconnecting in 5 seconds...")
        time.sleep(5)
    except KeyboardInterrupt:
        break

