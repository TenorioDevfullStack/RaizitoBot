import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram import Update

from bot.db import is_authorized_user_active, observe_authorized_user, upsert_authorized_user
from bot.handlers import (
    start_command, help_command, handle_message,
    add_task_command, list_tasks_command, complete_task_command,
    today_command, daily_command, event_command, confirm_event_command, cancel_event_command,
    reminders_command,
    search_command, app_status_command,
    handle_photo, handle_audio,
    gmail_command, drive_command, calendar_command, docs_command,
    remember_command, memory_command, forget_command,
    knowledge_command, emails_command,
    mission_command, missions_command, mission_status_command,
    mission_step_command, mission_confirm_command, mission_report_command,
    email_draft_command, drafts_command, draft_view_command, draft_delete_command,
    send_due_task_reminders, send_daily_summaries, send_meeting_reminders,
)

load_dotenv()


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _authorized_ids_from_env():
    ids = set()
    for raw in (os.getenv("AUTHORIZED_USER_IDS") or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ids.add(int(raw))
        except ValueError:
            continue
    return ids


def _user_full_name(user):
    parts = [user.first_name, user.last_name]
    return " ".join(part for part in parts if part)


async def authorization_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    env_authorized_ids = _authorized_ids_from_env()
    username = user.username
    full_name = _user_full_name(user)

    if user.id in env_authorized_ids:
        upsert_authorized_user(
            user.id,
            username=username,
            full_name=full_name,
            is_active=True,
            source="env",
            mark_seen=True,
        )
        return

    observe_authorized_user(user.id, username=username, full_name=full_name)
    if not _env_flag("ENFORCE_AUTHORIZED_USERS", False):
        return

    if is_authorized_user_active(user.id):
        return

    if update.effective_message:
        await update.effective_message.reply_text("Acesso nao autorizado para este bot.")
    raise ApplicationHandlerStop


def build_application():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN not found in environment")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(TypeHandler(Update, authorization_guard), group=-1)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", add_task_command))
    app.add_handler(CommandHandler("tasks", list_tasks_command))
    app.add_handler(CommandHandler("list", list_tasks_command))
    app.add_handler(CommandHandler("done", complete_task_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("reminders", reminders_command))
    app.add_handler(CommandHandler("event", event_command))
    app.add_handler(CommandHandler("confirm_event", confirm_event_command))
    app.add_handler(CommandHandler("cancel_event", cancel_event_command))
    app.add_handler(CommandHandler("remember", remember_command))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("knowledge", knowledge_command))
    app.add_handler(CommandHandler("mission", mission_command))
    app.add_handler(CommandHandler("missions", missions_command))
    app.add_handler(CommandHandler("mission_status", mission_status_command))
    app.add_handler(CommandHandler("mission_step", mission_step_command))
    app.add_handler(CommandHandler("mission_confirm", mission_confirm_command))
    app.add_handler(CommandHandler("mission_report", mission_report_command))
    app.add_handler(CommandHandler("emails", emails_command))
    app.add_handler(CommandHandler("email_draft", email_draft_command))
    app.add_handler(CommandHandler("drafts", drafts_command))
    app.add_handler(CommandHandler("draft_view", draft_view_command))
    app.add_handler(CommandHandler("draft_delete", draft_delete_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("gmail", gmail_command))
    app.add_handler(CommandHandler("drive", drive_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("docs", docs_command))
    app.add_handler(CommandHandler("app_status", app_status_command))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(send_due_task_reminders, interval=60, first=10)
        app.job_queue.run_repeating(send_daily_summaries, interval=60, first=20)
        app.job_queue.run_repeating(send_meeting_reminders, interval=300, first=30)

    return app
