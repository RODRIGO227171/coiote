from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import asyncio
import os

# --- CONFIGURAÇÕES ---
TOKEN = '7904567699:AAG8BkEFetdD6luPBxO1IdxXmUYWUDyC-pU'
LOG_GROUP_ID = -4660228290

IMAGE_PATH_MENU = 'menu.jpg'
IMAGE_PATH_SPAM = 'spam.jpg'
APK_PATH = 'infobuscas.apk'

# --- FUNÇÃO DE LOG ---
async def log_command(update: Update, comando: str):
    user = None
    chat = update.effective_chat

    if update.message:
        user = update.message.from_user
    elif update.callback_query:
        user = update.callback_query.from_user

    if user:
        username = f"@{user.username}" if user.username else "🙈 (sem username)"
        chat_type = "👥 Grupo" if chat.type in ['group', 'supergroup'] else "💬 Privado"
        horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        log_text = f"""
📢 <b>LOG DE COMANDO</b>
━━━━━━━━━━━━━━━━━━━━━
👤 <b>Nome:</b> {user.full_name}
🔗 <b>Username:</b> {username}
🆔 <b>ID do usuário:</b> <code>{user.id}</code>

💬 <b>Chat:</b> {chat_type}
🆔 <b>ID do chat:</b> <code>{chat.id}</code>

🕓 <b>Horário:</b> <code>{horario}</code>
📎 <b>Comando executado:</b> <code>{comando}</code>
"""
        print(log_text)

        # Envia para o grupo de logs
        try:
            await update.get_bot().send_message(
                chat_id=LOG_GROUP_ID,
                text=log_text,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Erro ao enviar log para grupo: {e}")

        # Se o usuário não tiver username, reencaminha a mensagem ou comando para o grupo de logs
        if not user.username:
            try:
                # Se for uma mensagem
                if update.message:
                    await update.message.forward(chat_id=LOG_GROUP_ID)
                # Se for uma callback (botão)
                elif update.callback_query:
                    await update.callback_query.message.forward(chat_id=LOG_GROUP_ID)
            except Exception as e:
                print(f"Erro ao reencaminhar a mensagem para o grupo de logs: {e}")

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_command(update, "/start")

    keyboard = [
        [InlineKeyboardButton("🚀 | reportar versão v1", callback_data='report_v1')],
        [InlineKeyboardButton("🚀 | reportar versão v2", url='https://t.me/addlist/kFrhlclRdRI4NGM0')],
        [InlineKeyboardButton("✍️ | buscar informações", callback_data='buscar_info')],
        [InlineKeyboardButton("📞 suporte", url='https://t.me/destacou?text=Prezado%28a%29%20Coiote%2C%20espero%20que%20esteja%20bem.%20Estou%20entrando%20em%20contato%20para%20solicitar%20sua%20ajuda%20com%20alguns%20relat%C3%B3rios%20que%20preciso%20gerar.%20Ouvi%20dizer%20que%20voc%C3%AA%20tem%20experi%C3%AAncia%20nesse%20tipo%20de%20tarefa%20e%20gostaria%20de%20saber%20mais%20sobre%20como%20posso%20contar%20com%20seu%20apoio.%20Fico%20%C3%A0%20disposi%C3%A7%C3%A3o%20para%20discutir%20os%20detalhes%20e%20saber%20qual%20seria%20o%20melhor%20procedimento%20para%20come%C3%A7ar.')
    ] ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(IMAGE_PATH_MENU, 'rb'),
        caption="👋 Bem-vindo(a) ao MisakaTools\n\nEscolha uma opção abaixo:",
        reply_markup=reply_markup
    )

# --- BOTÕES ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await log_command(update, f"Callback: {query.data}")

    if query.data == 'report_v1':
        aviso = await context.bot.send_message(chat_id=user_id, text="🚀 Enviando 1000 imagens...")
        for i in range(1000):
            try:
                await context.bot.send_photo(chat_id=user_id, photo=open(IMAGE_PATH_SPAM, 'rb'))
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"Erro ao enviar imagem {i}: {e}")
                break
        await aviso.delete()

    elif query.data == 'buscar_info':
        aviso = await context.bot.send_message(chat_id=user_id, text="📦 Enviando o aplicativo infobuscas.apk...")
        try:
            if not os.path.exists(APK_PATH):
                await context.bot.send_message(chat_id=user_id, text="❌ Arquivo APK não encontrado.")
                await aviso.delete()
                return
            await context.bot.send_document(chat_id=user_id, document=open(APK_PATH, 'rb'), filename="infobuscas.apk")
        except Exception as e:
            print(f"Erro ao enviar APK: {e}")
            await context.bot.send_message(chat_id=user_id, text="❌ Erro ao enviar o APK.")
        await aviso.delete()

# --- OPCIONAL: Captura de file_id de sticker ---
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    print(f"Sticker file_id: {sticker.file_id}")

# --- EXECUÇÃO DO BOT ---
if __name__ == '__main__':
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    print("🤖 Bot rodando...")
    app.run_polling()
