import os
from datetime import datetime, timezone
from typing import List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_DELEGATED_USER = os.getenv("GOOGLE_DELEGATED_USER")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DOCS_SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


def _get_credentials(scopes: List[str]):
    if not GOOGLE_SERVICE_ACCOUNT_FILE:
        raise ValueError("⚠️ GOOGLE_SERVICE_ACCOUNT_FILE is not configured.")

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
    )

    if GOOGLE_DELEGATED_USER:
        credentials = credentials.with_subject(GOOGLE_DELEGATED_USER)

    return credentials


def list_recent_emails(query: str | None = None, max_results: int = 5) -> str:
    """Fetch the most recent emails from Gmail."""
    credentials = _get_credentials(GMAIL_SCOPES)
    service = build("gmail", "v1", credentials=credentials)

    request = service.users().messages().list(userId="me", q=query or "", maxResults=max_results)
    response = request.execute()
    messages = response.get("messages", [])

    if not messages:
        return "Nenhum e-mail encontrado."

    formatted = "*E-mails recentes:*\n"
    for message in messages:
        msg_detail = service.users().messages().get(userId="me", id=message["id"], format="metadata",
                                                   metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in msg_detail.get("payload", {}).get("headers", [])}
        formatted += f"• *Assunto:* {headers.get('Subject', 'Sem assunto')}\n"
        formatted += f"  *De:* {headers.get('From', 'Desconhecido')}\n"
        formatted += f"  *Data:* {headers.get('Date', 'Sem data')}\n\n"

    return formatted


def list_drive_files(page_size: int = 5) -> str:
    credentials = _get_credentials(DRIVE_SCOPES)
    service = build("drive", "v3", credentials=credentials)

    results = service.files().list(pageSize=page_size, fields="files(id, name, mimeType, modifiedTime)").execute()
    items = results.get("files", [])

    if not items:
        return "Nenhum arquivo encontrado no Drive."

    formatted = "*Arquivos recentes no Drive:*\n"
    for item in items:
        modified = item.get("modifiedTime", "Desconhecido")
        formatted += f"• {item.get('name')} ({item.get('mimeType')}) — Atualizado em {modified}\n"

    return formatted


def list_upcoming_events(max_results: int = 5) -> str:
    credentials = _get_credentials(CALENDAR_SCOPES)
    service = build("calendar", "v3", credentials=credentials)

    now = datetime.now(timezone.utc).isoformat()
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])

    if not events:
        return "Nenhum evento futuro encontrado."

    formatted = "*Próximos eventos:*\n"
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        summary = event.get("summary", "(Sem título)")
        formatted += f"• {summary} — {start}\n"

    return formatted


def get_document_metadata(document_id: str) -> str:
    credentials = _get_credentials(DOCS_SCOPES)
    service = build("docs", "v1", credentials=credentials)

    doc = service.documents().get(documentId=document_id).execute()
    title = doc.get("title", "Sem título")

    content_elements: List[Dict] = doc.get("body", {}).get("content", [])
    paragraphs: List[str] = []
    for element in content_elements:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text_runs = [r.get("textRun", {}).get("content", "") for r in paragraph.get("elements", [])]
        combined = "".join(text_runs).strip()
        if combined:
            paragraphs.append(combined)

    preview = "\n".join(paragraphs[:3])
    formatted_preview = preview if preview else "Pré-visualização não disponível."

    return f"*Documento:* {title}\n\n{formatted_preview}"
