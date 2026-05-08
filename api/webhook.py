import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler

from telegram import Update

from bot.app import build_application
from bot.db import init_db

logger = logging.getLogger(__name__)


async def _process_update(update_data):
    init_db()
    app = build_application()
    await app.initialize()
    try:
        update = Update.de_json(update_data, app.bot)
        await app.process_update(update)
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

    def do_GET(self):
        self._send_json(200, {"ok": True, "service": "telegram-webhook"})

    def do_POST(self):
        expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        received_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token")

        if expected_secret and received_secret != expected_secret:
            self._send_json(403, {"ok": False, "error": "invalid webhook secret"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            update_data = json.loads(raw_body.decode("utf-8"))
            asyncio.run(_process_update(update_data))
            self._send_json(200, {"ok": True})
        except Exception as e:
            logger.exception("Failed to process Telegram update")
            self._send_json(500, {"ok": False, "error": str(e)})
