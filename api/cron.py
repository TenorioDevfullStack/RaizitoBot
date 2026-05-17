import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace

from bot.app import build_application
from bot.db import init_db
from bot.handlers import send_daily_summaries, send_due_task_reminders, send_meeting_reminders

logger = logging.getLogger(__name__)


async def _run_scheduled_jobs():
    init_db()
    app = build_application()
    await app.initialize()
    try:
        context = SimpleNamespace(bot=app.bot)
        await send_due_task_reminders(context)
        await send_daily_summaries(context)
        await send_meeting_reminders(context)
    finally:
        await app.shutdown()


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected_secret = os.getenv("CRON_SECRET")
        if not expected_secret:
            return True
        authorization = self.headers.get("Authorization", "")
        cron_secret = self.headers.get("X-Cron-Secret", "")
        return authorization == f"Bearer {expected_secret}" or cron_secret == expected_secret

    def _handle(self):
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "invalid cron secret"})
            return

        try:
            asyncio.run(_run_scheduled_jobs())
            self._send_json(200, {"ok": True})
        except Exception as e:
            logger.exception("Failed to run scheduled jobs")
            self._send_json(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()
