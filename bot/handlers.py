import os
from telegram import Update
from telegram.ext import ContextTypes
from bot.ai_service import get_gemini_response, analyze_image, transcribe_audio
from bot.db import add_task, get_tasks, complete_task, log_conversation, get_conversation_history
from bot.web_search import google_search
from bot.external_integration import external_client
from bot.google_services import (
    list_recent_emails,
    list_drive_files,
    list_upcoming_events,
    get_document_metadata,
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am your AI Assistant. I can help you with tasks, reminders, questions, and more.\n"
        "Try sending me a message or use /help to see what I can do."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
*Commands:*
/start - Start the bot
/help - Show this help
/task <text> - Add a new task
/list - List pending tasks
/done <id> - Mark a task as completed
/search <query> - Search the web
/gmail [query] - List recent emails filtered by query (optional)
/drive - List recent Drive files
/calendar - List upcoming events
/docs <document_id> - Preview a Google Docs document
/app_status - Check external app status

*Features:*
- Conversas com memória: mantenho o contexto das últimas mensagens.
- Send me any text to chat with AI.
- Send me a photo to analyze it.
- Send me a voice note to transcribe and answer.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    history = get_conversation_history(user_id)
    response = get_gemini_response(user_text, history=history)

    log_conversation(user_id, "user", user_text)
    log_conversation(user_id, "assistant", response)

    await update.message.reply_text(response)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    from io import BytesIO
    bio = BytesIO()
    await photo_file.download_to_memory(bio)
    bio.seek(0)
    image_data = bio.read()

    caption = update.message.caption or "Describe this image"
    await update.message.reply_text("👀 Analyzing image...")

    import PIL.Image
    img = PIL.Image.open(BytesIO(image_data))

    response = analyze_image(img, caption)
    await update.message.reply_text(response)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🎤 Ouvindo...")

    voice = update.message.voice or update.message.audio
    file_id = voice.file_id
    new_file = await context.bot.get_file(file_id)

    file_path = f"voice_{file_id}.ogg"
    await new_file.download_to_drive(file_path)

    try:
        text = transcribe_audio(file_path)

        if text.startswith("Error"):
            await status_msg.edit_text(f"❌ {text}")
            return

        await status_msg.edit_text(f"🗣️ *Você disse:* \"{text}\"\n\n🤔 *Pensando...*", parse_mode='Markdown')

        user_id = update.effective_user.id
        history = get_conversation_history(user_id)
        response = get_gemini_response(text, history=history)

        log_conversation(user_id, "user", text)
        log_conversation(user_id, "assistant", response)

        await update.message.reply_text(response)

    except Exception as e:
        await status_msg.edit_text(f"Error processing audio: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /task <task description>")
        return

    task_id = add_task(user_id, text)
    await update.message.reply_text(f"✅ Task added! (ID: {task_id})")

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_tasks(user_id)

    if not tasks:
        await update.message.reply_text("No pending tasks.")
        return

    msg = "*Your Tasks:*\n"
    for t in tasks:
        msg += f"{t[0]}. {t[1]}\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /done <task_id>")
        return
    try:
        task_id = int(context.args[0])
        success = complete_task(task_id, user_id)
        if success:
            await update.message.reply_text(f"✅ Task {task_id} marked as done.")
        else:
            await update.message.reply_text(f"❌ Task {task_id} not found.")
    except ValueError:
        await update.message.reply_text("Invalid Task ID.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    await update.message.reply_text(f"🔍 Searching for '{query}'...")
    result = google_search(query)
    await update.message.reply_text(result, parse_mode='Markdown')

async def gmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else None
    try:
        result = list_recent_emails(query=query)
    except Exception as e:
        result = f"Erro ao acessar o Gmail: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def drive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = list_drive_files()
    except Exception as e:
        result = f"Erro ao acessar o Drive: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = list_upcoming_events()
    except Exception as e:
        result = f"Erro ao acessar o Calendar: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def docs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /docs <document_id>")
        return
    document_id = context.args[0]
    try:
        result = get_document_metadata(document_id)
    except Exception as e:
        result = f"Erro ao acessar o Docs: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def app_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Connecting to external app...")
    data = external_client.get_dashboard_data()
    if isinstance(data, dict):
        msg = f"*App Status:*\nStatus: {data.get('status')}\nPending Orders: {data.get('pending_orders')}"
    else:
        msg = f"Error: {data}"

    await update.message.reply_text(msg, parse_mode='Markdown')
