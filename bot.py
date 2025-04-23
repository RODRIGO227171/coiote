from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import asyncio
import os

# --- CONFIGURAÇÕES ---
TOKEN = '7904567699:AAG8BkEFetdD6luPBxO1IdxXmUYWUDyC-pU'
IMAGE_PATH_MENU = 'menu.jpg'      # Imagem do menu (coloque aqui seu arquivo correto)
IMAGE_PATH_SPAM = 'spam.jpg'      # Imagem que será spamada
APK_PATH = 'infobuscas.apk'       # Nome do arquivo .apk
STICKER_FILE_IDS = [              # IDs de stickers
    'CAACAgUAAxkBAAIBh2YxNYvWQ4Hy9V-UaNz0EAlCMsy_AALbAQACN6CIVeYG1HH8yoW3LwQ',
    'CAACAgUAAxkBAAIBiGYxNaOm79etEdRZx9G7ssbsO9qlAALcAQACN6CIVd6Zx8kJYqk4LwQ',
    'CAACAgUAAxkBAAIBiWYxNbAk2mLZ7GyP01ZCu1E9cPSMAALdAQACN6CIVYUnq0DoHoD-LwQ'
]

# --- LOG DE COMANDOS ---
async def log_command(update: Update, comando: str):
    user = None
    chat = update.effective_chat

    if update.message:
        user = update.message.from_user
    elif update.callback_query:
        user = update.callback_query.from_user

    if user:
        username = f"@{user.username}" if user.username else "(sem username)"
        chat_type = "Grupo" if chat.type in ['group', 'supergroup'] else "Chat privado"
        print(f"""
Comando executado: {comando}
Usuário: {user.full_name} ({username})
ID do usuário: {user.id}
Chat: {chat_type}
ID do chat: {chat.id}
----------------------------------------
""")

# --- COMANDO /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_command(update, "/start")

    keyboard = [
        [InlineKeyboardButton("🚀 | reportar versão v1", callback_data='report_v1')],
        [InlineKeyboardButton("🚀 | reportar versão v2", callback_data='report_v2')],
        [InlineKeyboardButton("✍️ | buscar informações", callback_data='buscar_info')],
        [InlineKeyboardButton("📞 suporte", url='https://t.me/destacou')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(IMAGE_PATH_MENU, 'rb'),
        caption="👋 Bem-vindo(a) ao MisakaTools\n\nEscolha uma opção abaixo:",
        reply_markup=reply_markup
    )

# --- TRATADOR DE BOTÕES ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    await log_command(update, f"Callback: {query.data}")

    if query.data == 'report_v1':
        await context.bot.send_message(chat_id=user_id, text="🚀 Enviando 1000 imagens...")
        for i in range(1000):
            try:
                await context.bot.send_photo(chat_id=user_id, photo=open(IMAGE_PATH_SPAM, 'rb'))
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"Erro ao enviar imagem {i}: {e}")
                break

    elif query.data == 'report_v2':
        await context.bot.send_message(chat_id=user_id, text="🚀 Enviando 2000 mensagens...")
        for i in range(2000):
            try:
                await context.bot.send_message(chat_id=user_id, text="ping")
                await asyncio.sleep(0.02)
            except Exception as e:
                print(f"Erro ao enviar mensagem {i}: {e}")
                break

    elif query.data == 'buscar_info':
        try:
            if not os.path.exists(APK_PATH):
                await context.bot.send_message(chat_id=user_id, text="❌ Arquivo APK não encontrado.")
                return
            await context.bot.send_message(chat_id=user_id, text="📦 Enviando o aplicativo infobuscas.apk...")
            await context.bot.send_document(chat_id=user_id, document=open(APK_PATH, 'rb'), filename="infobuscas.apk")
        except Exception as e:
            print(f"Erro ao enviar APK: {e}")
            await context.bot.send_message(chat_id=user_id, text="❌ Erro ao enviar o APK.")

# --- OPCIONAL: CAPTURAR FILE_ID DE STICKERS ---
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    print(f"Sticker file_id: {sticker.file_id}")

# --- EXECUÇÃO DO BOT ---
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))  # para capturar file_id, opcional
app.run_polling()
