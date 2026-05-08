import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
from bot.ai_service import get_gemini_response, analyze_image, transcribe_audio
from bot.db import (
    add_memory,
    add_task,
    clear_memories,
    complete_task,
    delete_memory,
    get_conversation_history,
    get_memories,
    get_tasks,
    log_conversation,
)
from bot.web_search import google_search
from bot.external_integration import external_client
from bot.google_services import (
    list_recent_emails,
    list_drive_files,
    list_upcoming_events,
    get_document_metadata,
)

MEMORY_PREFIXES = (
    "lembre que ",
    "lembra que ",
    "lembre-se que ",
    "memorize ",
    "guarde que ",
    "guarda que ",
    "salve na memoria ",
    "salve na memória ",
)

MEMORY_LIST_REQUESTS = (
    "o que voce lembra de mim?",
    "o que você lembra de mim?",
    "o que voce lembra?",
    "o que você lembra?",
    "minhas memorias",
    "minhas memórias",
    "quais memorias voce tem?",
    "quais memórias você tem?",
)


def _extract_memory_text(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in MEMORY_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def _format_memories(memories):
    if not memories:
        return "Ainda nao tenho memorias salvas sobre voce."

    lines = ["Memorias salvas:"]
    lines.extend(f"{memory['id']}. {memory['content']}" for memory in memories)
    return "\n".join(lines)


def _build_memory_context(user_id):
    memories = get_memories(user_id)
    if not memories:
        return None

    memory_lines = [f"- {memory['content']}" for memory in reversed(memories)]
    return (
        "Contexto persistente sobre o usuario. Use essas memorias apenas quando "
        "forem relevantes para responder melhor. Nao diga que esta lendo uma "
        "base de memorias, a menos que o usuario pergunte.\n"
        + "\n".join(memory_lines)
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Opa! Eu sou seu assistente pessoal com IA.\n"
        "Posso conversar, guardar memorias, organizar tarefas, buscar informacoes e acessar Google Workspace.\n"
        "Tente: lembre que meu cliente principal e a Loja X"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
*Commands:*
/start - Start the bot
/help - Show this help
/task <text> - Add a new task
/list - List pending tasks
/done <id> - Mark a task as completed
/remember <text> - Save a persistent memory
/memory - List saved memories
/memory add <text> - Save a persistent memory
/memory delete <id> - Delete one memory
/memory clear - Delete all your memories
/forget <id> - Delete one memory
/search <query> - Search the web
/gmail [query] - List recent emails filtered by query (optional)
/drive - List recent Drive files
/calendar - List upcoming events
/docs <document_id> - Preview a Google Docs document
/app_status - Check external app status

*Features:*
- Conversas com memória: mantenho o contexto das últimas mensagens.
- Memoria pessoal persistente: diga "lembre que..." para eu guardar fatos importantes.
- Send me any text to chat with AI.
- Send me a photo to analyze it.
- Send me a voice note to transcribe and answer.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    memory_text = _extract_memory_text(user_text)
    if memory_text:
        memory_id = add_memory(user_id, memory_text)
        await update.message.reply_text(f"Memoria salva. ID: {memory_id}")
        return

    if user_text.strip().lower() in MEMORY_LIST_REQUESTS:
        await update.message.reply_text(_format_memories(get_memories(user_id)))
        return

    history = get_conversation_history(user_id)
    response = get_gemini_response(
        user_text,
        history=history,
        system_context=_build_memory_context(user_id),
    )

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

    file_path = os.path.join(tempfile.gettempdir(), f"voice_{file_id}.ogg")
    await new_file.download_to_drive(file_path)

    try:
        text = transcribe_audio(file_path)

        if text.startswith("Error"):
            await status_msg.edit_text(f"❌ {text}")
            return

        await status_msg.edit_text(f"🗣️ *Você disse:* \"{text}\"\n\n🤔 *Pensando...*", parse_mode='Markdown')

        user_id = update.effective_user.id
        memory_text = _extract_memory_text(text)
        if memory_text:
            memory_id = add_memory(user_id, memory_text)
            await update.message.reply_text(f"Memoria salva. ID: {memory_id}")
            return

        history = get_conversation_history(user_id)
        response = get_gemini_response(
            text,
            history=history,
            system_context=_build_memory_context(user_id),
        )

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

async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Uso: /remember <informacao para lembrar>")
        return

    memory_id = add_memory(user_id, text)
    await update.message.reply_text(f"Memoria salva. ID: {memory_id}")

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args or context.args[0].lower() in {"list", "listar", "ver"}:
        await update.message.reply_text(_format_memories(get_memories(user_id)))
        return

    action = context.args[0].lower()
    if action in {"add", "save", "salvar", "lembrar"}:
        text = " ".join(context.args[1:]).strip()
        if not text:
            await update.message.reply_text("Uso: /memory add <informacao para lembrar>")
            return
        memory_id = add_memory(user_id, text)
        await update.message.reply_text(f"Memoria salva. ID: {memory_id}")
        return

    if action in {"delete", "del", "remove", "apagar", "forget", "esquecer"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /memory delete <id>")
            return
        try:
            memory_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de memoria invalido.")
            return
        if delete_memory(memory_id, user_id):
            await update.message.reply_text(f"Memoria {memory_id} apagada.")
        else:
            await update.message.reply_text(f"Memoria {memory_id} nao encontrada.")
        return

    if action in {"clear", "limpar", "apagar_tudo"}:
        total = clear_memories(user_id)
        await update.message.reply_text(f"{total} memoria(s) apagada(s).")
        return

    await update.message.reply_text(
        "Uso:\n"
        "/memory\n"
        "/memory add <informacao>\n"
        "/memory delete <id>\n"
        "/memory clear"
    )

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /forget <id>")
        return
    try:
        memory_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de memoria invalido.")
        return

    if delete_memory(memory_id, user_id):
        await update.message.reply_text(f"Memoria {memory_id} apagada.")
    else:
        await update.message.reply_text(f"Memoria {memory_id} nao encontrada.")

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
