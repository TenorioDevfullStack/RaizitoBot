import html
import json
import logging
import os
import secrets
import threading
from collections import Counter, deque
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from bot.db import (
    create_database_backup,
    get_database_path,
    get_knowledge_backend,
    get_operational_counts,
    list_authorized_users,
    list_database_backups,
    list_user_settings,
    upsert_authorized_user,
    upsert_user_settings,
)
from bot.vector_store import supabase_vector_store_configured


logger = logging.getLogger(__name__)
STARTED_AT = datetime.utcnow()
LOG_RECORDS = deque(maxlen=300)
_LOG_HANDLER_INSTALLED = False


class InMemoryLogHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_RECORDS.append({
                "created_at": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            })
        except Exception:
            pass


def configure_admin_logging():
    global _LOG_HANDLER_INSTALLED
    if _LOG_HANDLER_INSTALLED:
        return
    handler = InMemoryLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)
    _LOG_HANDLER_INSTALLED = True


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _h(value):
    return html.escape("" if value is None else str(value), quote=True)


def _runtime_seconds():
    return int((datetime.utcnow() - STARTED_AT).total_seconds())


def _format_bytes(size):
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def _integration_for_log(record):
    text = f"{record.get('logger', '')} {record.get('message', '')}".lower()
    checks = {
        "telegram": ("telegram", "httpx"),
        "gemini": ("gemini", "generativelanguage"),
        "supabase": ("supabase", "vector"),
        "google": ("gmail", "drive", "calendar", "docs", "googleapiclient"),
        "search": ("search", "custom search"),
        "database": ("sqlite", "database", "db.py"),
        "external_app": ("external", "app_status"),
    }
    for name, needles in checks.items():
        if any(needle in text for needle in needles):
            return name
    return "app"


def _error_summary():
    summary = Counter()
    for record in LOG_RECORDS:
        if record["level"] in {"WARNING", "ERROR", "CRITICAL"}:
            summary[_integration_for_log(record)] += 1
    return dict(sorted(summary.items()))


def _status_payload():
    return {
        "service": "raizitobot",
        "uptime_seconds": _runtime_seconds(),
        "started_at": STARTED_AT.isoformat(timespec="seconds"),
        "db_path": get_database_path(),
        "vector_backend": get_knowledge_backend(),
        "supabase_configured": supabase_vector_store_configured(),
        "telegram_token_set": bool(os.getenv("TELEGRAM_TOKEN")),
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "admin_panel_enabled": _env_flag("ADMIN_PANEL_ENABLED"),
        "auth_enforced": _env_flag("ENFORCE_AUTHORIZED_USERS"),
        "counts": get_operational_counts(),
        "error_summary": _error_summary(),
    }


def _page(title, active, body):
    nav_items = [
        ("status", "Status", "/"),
        ("logs", "Logs", "/logs"),
        ("users", "Usuarios", "/users"),
        ("settings", "Configuracoes", "/settings"),
        ("backup", "Backup", "/backup"),
    ]
    nav = "".join(
        f'<a class="{ "active" if key == active else "" }" href="{href}">{label}</a>'
        for key, label, href in nav_items
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(title)} - RaizitoBot</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #0f766e;
      --danger: #b42318;
      --warn: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      background: #172026;
      color: #fff;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    header h1 {{ font-size: 18px; margin: 0; }}
    nav {{
      background: #fff;
      border-bottom: 1px solid var(--line);
      padding: 0 24px;
      display: flex;
      gap: 4px;
      overflow-x: auto;
    }}
    nav a {{
      color: var(--muted);
      text-decoration: none;
      padding: 12px 14px;
      border-bottom: 2px solid transparent;
      white-space: nowrap;
    }}
    nav a.active {{
      color: var(--accent);
      border-color: var(--accent);
      font-weight: 650;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    h3 {{ margin: 18px 0 10px; font-size: 15px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
    .metric {{ border-left: 3px solid var(--accent); padding: 8px 10px; background: #f8fbfb; }}
    .metric strong {{ display: block; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    pre {{ overflow: auto; background: #101820; color: #e6edf3; padding: 12px; border-radius: 8px; }}
    label {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }}
    input, select, textarea {{
      width: 100%;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }}
    textarea {{ min-height: 70px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; align-items: end; }}
    button, .button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      padding: 10px 13px;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
      font-weight: 650;
    }}
    .muted {{ color: var(--muted); }}
    .ok {{ color: var(--accent); font-weight: 650; }}
    .bad {{ color: var(--danger); font-weight: 650; }}
    .warn {{ color: var(--warn); font-weight: 650; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #edf2f7; }}
    @media (max-width: 680px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      main {{ padding: 14px; }}
      th, td {{ font-size: 13px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>RaizitoBot Operacao</h1>
    <span class="muted">online desde {_h(STARTED_AT.isoformat(timespec="seconds"))}</span>
  </header>
  <nav>{nav}</nav>
  <main>{body}</main>
</body>
</html>"""


def _login_page(error=None):
    message = f'<p class="bad">{_h(error)}</p>' if error else ""
    body = f"""
<section>
  <h2>Acesso ao painel</h2>
  {message}
  <form method="post" action="/login">
    <label for="token">Token administrativo</label>
    <input id="token" name="token" type="password" autocomplete="current-password">
    <p><button type="submit">Entrar</button></p>
  </form>
</section>
"""
    return _page("Login", "status", body)


class AdminPanelHandler(BaseHTTPRequestHandler):
    server_version = "RaizitoBotAdmin/1.0"

    def log_message(self, fmt, *args):
        logger.info("admin panel: " + fmt, *args)

    def _token(self):
        return os.getenv("ADMIN_PANEL_TOKEN") or ""

    def _cookie_token(self):
        raw_cookie = self.headers.get("Cookie", "")
        parsed = cookies.SimpleCookie()
        try:
            parsed.load(raw_cookie)
        except cookies.CookieError:
            return ""
        morsel = parsed.get("admin_token")
        return unquote(morsel.value) if morsel else ""

    def _query_token(self):
        query = parse_qs(urlparse(self.path).query)
        return (query.get("token") or [""])[0]

    def _authenticated(self):
        token = self._token()
        if not token:
            return False
        provided = self._cookie_token() or self._query_token() or self.headers.get("X-Admin-Token", "")
        return secrets.compare_digest(provided, token)

    def _read_form(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}

    def _send(self, status, body, content_type="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _require_auth(self):
        if self.path.startswith("/login"):
            return True
        if self._authenticated():
            return True
        self._send(401, _login_page("Informe o token administrativo."))
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self._send(200, _login_page())
            return
        if not self._require_auth():
            return

        routes = {
            "/": self._render_status,
            "/status": self._render_status,
            "/logs": self._render_logs,
            "/users": self._render_users,
            "/settings": self._render_settings,
            "/backup": self._render_backup,
            "/api/status": self._api_status,
            "/api/logs": self._api_logs,
            "/download": self._download_backup,
        }
        handler = routes.get(parsed.path)
        if not handler:
            self._send(404, _page("Nao encontrado", "status", "<section><h2>Pagina nao encontrada</h2></section>"))
            return
        handler()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            form = self._read_form()
            if secrets.compare_digest(form.get("token", ""), self._token()):
                self._redirect(
                    "/",
                    headers={"Set-Cookie": f"admin_token={quote(self._token(), safe='')}; HttpOnly; SameSite=Lax; Path=/"},
                )
                return
            self._send(401, _login_page("Token invalido."))
            return
        if not self._require_auth():
            return
        if parsed.path == "/users":
            self._save_user()
            return
        if parsed.path == "/settings":
            self._save_settings()
            return
        if parsed.path == "/backup":
            create_database_backup(os.getenv("ADMIN_PANEL_BACKUP_DIR", "data/backups"))
            self._redirect("/backup")
            return
        self._send(404, _page("Nao encontrado", "status", "<section><h2>Pagina nao encontrada</h2></section>"))

    def _redirect(self, location, headers=None):
        self.send_response(303)
        self.send_header("Location", location)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _render_status(self):
        payload = _status_payload()
        counts = payload["counts"]
        status_items = [
            ("Backend vetorial", payload["vector_backend"]),
            ("Supabase", "configurado" if payload["supabase_configured"] else "nao configurado"),
            ("Auth usuarios", "ativo" if payload["auth_enforced"] else "observacao"),
            ("DB", payload["db_path"]),
        ]
        metric_html = "".join(
            f'<div class="metric"><span>{_h(label)}</span><strong>{_h(value)}</strong></div>'
            for label, value in status_items
        )
        counts_html = "".join(
            f"<tr><td>{_h(name)}</td><td>{_h(value)}</td></tr>"
            for name, value in counts.items()
        )
        error_html = "".join(
            f"<tr><td>{_h(name)}</td><td>{count}</td></tr>"
            for name, count in payload["error_summary"].items()
        ) or '<tr><td colspan="2" class="ok">Sem avisos ou erros recentes.</td></tr>'
        body = f"""
<section>
  <h2>Status</h2>
  <div class="grid">{metric_html}</div>
</section>
<section>
  <h2>Contadores</h2>
  <table><tbody>{counts_html}</tbody></table>
</section>
<section>
  <h2>Erros por integracao</h2>
  <table><thead><tr><th>Integracao</th><th>Eventos</th></tr></thead><tbody>{error_html}</tbody></table>
</section>
"""
        self._send(200, _page("Status", "status", body))

    def _render_logs(self):
        rows = "".join(
            f"<tr><td>{_h(item['created_at'])}</td><td>{_h(item['level'])}</td>"
            f"<td>{_h(item['logger'])}</td><td><code>{_h(item['message'])}</code></td></tr>"
            for item in reversed(LOG_RECORDS)
        ) or '<tr><td colspan="4" class="muted">Sem logs recentes.</td></tr>'
        body = f"""
<section>
  <h2>Logs recentes</h2>
  <table>
    <thead><tr><th>Horario</th><th>Nivel</th><th>Logger</th><th>Mensagem</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""
        self._send(200, _page("Logs", "logs", body))

    def _render_users(self):
        rows = "".join(
            f"<tr><td>{user['user_id']}</td><td>{_h(user.get('username'))}</td>"
            f"<td>{_h(user.get('full_name'))}</td><td>{_h(user.get('source'))}</td>"
            f"<td>{'ativo' if user['is_active'] else 'observado'}</td>"
            f"<td>{_h(user.get('last_seen_at'))}</td><td>{_h(user.get('note'))}</td></tr>"
            for user in list_authorized_users()
        ) or '<tr><td colspan="7" class="muted">Nenhum usuario observado.</td></tr>'
        body = f"""
<section>
  <h2>Usuarios autorizados</h2>
  <form method="post" action="/users" class="form-grid">
    <div><label>User ID</label><input name="user_id" required></div>
    <div><label>Username</label><input name="username"></div>
    <div><label>Nome</label><input name="full_name"></div>
    <div><label>Status</label><select name="is_active"><option value="1">Ativo</option><option value="0">Observado</option></select></div>
    <div><label>Nota</label><input name="note"></div>
    <div><button type="submit">Salvar usuario</button></div>
  </form>
</section>
<section>
  <table>
    <thead><tr><th>ID</th><th>Username</th><th>Nome</th><th>Origem</th><th>Status</th><th>Visto</th><th>Nota</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""
        self._send(200, _page("Usuarios", "users", body))

    def _render_settings(self):
        rows = "".join(
            f"<tr><td>{item['user_id']}</td><td>{_h(item['chat_id'])}</td>"
            f"<td>{'ativo' if item['daily_summary_enabled'] else 'off'}</td>"
            f"<td>{_h(item['daily_summary_time'])}</td>"
            f"<td>{'ativo' if item['meeting_reminders_enabled'] else 'off'}</td>"
            f"<td>{item['meeting_reminder_minutes']}</td></tr>"
            for item in list_user_settings()
        ) or '<tr><td colspan="6" class="muted">Nenhuma configuracao registrada.</td></tr>'
        body = f"""
<section>
  <h2>Configuracoes por usuario</h2>
  <form method="post" action="/settings" class="form-grid">
    <div><label>User ID</label><input name="user_id" required></div>
    <div><label>Chat ID</label><input name="chat_id"></div>
    <div><label>Resumo diario</label><select name="daily_summary_enabled"><option value="">Manter</option><option value="1">Ativo</option><option value="0">Off</option></select></div>
    <div><label>Horario</label><input name="daily_summary_time" placeholder="08:00"></div>
    <div><label>Avisos reuniao</label><select name="meeting_reminders_enabled"><option value="">Manter</option><option value="1">Ativo</option><option value="0">Off</option></select></div>
    <div><label>Minutos</label><input name="meeting_reminder_minutes" placeholder="15"></div>
    <div><button type="submit">Salvar configuracao</button></div>
  </form>
</section>
<section>
  <table>
    <thead><tr><th>User ID</th><th>Chat</th><th>Resumo</th><th>Horario</th><th>Reunioes</th><th>Minutos</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""
        self._send(200, _page("Configuracoes", "settings", body))

    def _render_backup(self):
        rows = "".join(
            f'<tr><td>{_h(item["name"])}</td><td>{_h(_format_bytes(item["size_bytes"]))}</td>'
            f'<td>{_h(item["modified_at"])}</td>'
            f'<td><a class="button" href="/download?name={quote(item["name"])}">Baixar</a></td></tr>'
            for item in list_database_backups(os.getenv("ADMIN_PANEL_BACKUP_DIR", "data/backups"))
        ) or '<tr><td colspan="4" class="muted">Nenhum backup encontrado.</td></tr>'
        body = f"""
<section>
  <h2>Backup do banco</h2>
  <form method="post" action="/backup">
    <button type="submit">Criar backup agora</button>
  </form>
</section>
<section>
  <table>
    <thead><tr><th>Arquivo</th><th>Tamanho</th><th>Modificado</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""
        self._send(200, _page("Backup", "backup", body))

    def _save_user(self):
        form = self._read_form()
        try:
            user_id = int(form.get("user_id", ""))
        except ValueError:
            self._redirect("/users")
            return
        upsert_authorized_user(
            user_id,
            username=form.get("username") or None,
            full_name=form.get("full_name") or None,
            note=form.get("note") or None,
            is_active=form.get("is_active") == "1",
            source="admin",
        )
        self._redirect("/users")

    def _save_settings(self):
        form = self._read_form()
        try:
            user_id = int(form.get("user_id", ""))
        except ValueError:
            self._redirect("/settings")
            return

        def maybe_int(name):
            value = form.get(name)
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                return None

        def maybe_bool(name):
            value = form.get(name)
            if value == "":
                return None
            return value == "1"

        upsert_user_settings(
            user_id,
            chat_id=maybe_int("chat_id"),
            daily_summary_enabled=maybe_bool("daily_summary_enabled"),
            daily_summary_time=form.get("daily_summary_time") or None,
            meeting_reminders_enabled=maybe_bool("meeting_reminders_enabled"),
            meeting_reminder_minutes=maybe_int("meeting_reminder_minutes"),
        )
        self._redirect("/settings")

    def _api_status(self):
        self._send(200, json.dumps(_status_payload()), content_type="application/json")

    def _api_logs(self):
        self._send(200, json.dumps(list(LOG_RECORDS)), content_type="application/json")

    def _download_backup(self):
        parsed = urlparse(self.path)
        name = unquote((parse_qs(parsed.query).get("name") or [""])[0])
        safe_name = Path(name).name
        backup_dir = Path(os.getenv("ADMIN_PANEL_BACKUP_DIR", "data/backups"))
        path = backup_dir / safe_name
        if not safe_name or not path.exists() or path.parent.resolve() != backup_dir.resolve():
            self._send(404, "Backup nao encontrado.", content_type="text/plain; charset=utf-8")
            return
        data = path.read_bytes()
        self._send(
            200,
            data,
            content_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )


def start_admin_panel():
    configure_admin_logging()
    if not _env_flag("ADMIN_PANEL_ENABLED", False):
        logger.info("Admin panel disabled.")
        return None
    if not os.getenv("ADMIN_PANEL_TOKEN"):
        logger.warning("ADMIN_PANEL_ENABLED=true but ADMIN_PANEL_TOKEN is missing; panel not started.")
        return None

    host = os.getenv("ADMIN_PANEL_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("ADMIN_PANEL_PORT", "8080"))
    except ValueError:
        port = 8080

    server = ThreadingHTTPServer((host, port), AdminPanelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Admin panel listening on %s:%s", host, port)
    return server
