import os
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_DELEGATED_USER = os.getenv("GOOGLE_DELEGATED_USER")
GOOGLE_CALENDAR_TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Sao_Paulo")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
DOCS_SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


def _get_credentials(scopes: List[str]):
    json_creds = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if json_creds:
        import json
        try:
            creds_dict = json.loads(json_creds)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=scopes
            )
        except json.JSONDecodeError as e:
             raise ValueError(f"⚠️ Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
    elif GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
    else:
        raise ValueError("⚠️ No valid Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE.")

    if GOOGLE_DELEGATED_USER:
        credentials = credentials.with_subject(GOOGLE_DELEGATED_USER)

    return credentials


def list_recent_emails(query: str | None = None, max_results: int = 5) -> str:
    """Fetch the most recent emails from Gmail."""
    emails = get_recent_emails(query=query, max_results=max_results)

    if not emails:
        return "Nenhum e-mail encontrado."

    formatted = "*E-mails recentes:*\n"
    for email in emails:
        formatted += f"• *ID:* `{email['id']}`\n"
        formatted += f"  *Assunto:* {email['subject']}\n"
        formatted += f"  *De:* {email['from']}\n"
        formatted += f"  *Data:* {email['date']}\n"
        if email.get("snippet"):
            formatted += f"  *Trecho:* {email['snippet']}\n"
        formatted += "\n"

    return formatted


def _gmail_service():
    credentials = _get_credentials(GMAIL_SCOPES)
    return build("gmail", "v1", credentials=credentials)


def _message_headers(message_detail: Dict) -> Dict:
    headers = message_detail.get("payload", {}).get("headers", [])
    return {header["name"].lower(): header.get("value", "") for header in headers}


def get_recent_emails(query: str | None = None, max_results: int = 10) -> List[Dict]:
    service = _gmail_service()
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query or "", maxResults=max_results)
        .execute()
    )
    messages = response.get("messages", [])
    emails = []

    for message in messages:
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        headers = _message_headers(detail)
        emails.append({
            "id": detail.get("id", message["id"]),
            "thread_id": detail.get("threadId"),
            "from": headers.get("from", "Desconhecido"),
            "subject": headers.get("subject", "Sem assunto"),
            "date": headers.get("date", "Sem data"),
            "snippet": detail.get("snippet", ""),
        })

    return emails


def get_email_metadata(message_id: str) -> Dict:
    service = _gmail_service()
    detail = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date", "To", "Cc"],
        )
        .execute()
    )
    headers = _message_headers(detail)
    return {
        "id": detail.get("id", message_id),
        "thread_id": detail.get("threadId"),
        "from": headers.get("from", "Desconhecido"),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "subject": headers.get("subject", "Sem assunto"),
        "date": headers.get("date", "Sem data"),
        "snippet": detail.get("snippet", ""),
    }


def list_drive_files(page_size: int = 5) -> str:
    items = get_drive_files(page_size=page_size)

    if not items:
        return "Nenhum arquivo encontrado no Drive."

    formatted = "*Arquivos recentes no Drive:*\n"
    for item in items:
        modified = item.get("modifiedTime", "Desconhecido")
        formatted += f"• `{item.get('id')}` - {item.get('name')} ({item.get('mimeType')}) — Atualizado em {modified}\n"

    return formatted


def _drive_service():
    credentials = _get_credentials(DRIVE_SCOPES)
    return build("drive", "v3", credentials=credentials)


def get_drive_files(query: str | None = None, page_size: int = 10) -> List[Dict]:
    service = _drive_service()
    params = {
        "pageSize": page_size,
        "fields": "files(id, name, mimeType, modifiedTime, webViewLink, size)",
        "orderBy": "modifiedTime desc",
    }
    if query:
        safe_query = query.replace("'", "\\'")
        params["q"] = f"name contains '{safe_query}' and trashed = false"
    results = service.files().list(**params).execute()
    return results.get("files", [])


def get_drive_file_metadata(file_id: str) -> Dict:
    service = _drive_service()
    return (
        service.files()
        .get(fileId=file_id, fields="id, name, mimeType, modifiedTime, webViewLink, size")
        .execute()
    )


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


def get_events_between(start_dt: datetime, end_dt: datetime, max_results: int = 20) -> List[Dict]:
    credentials = _get_credentials(CALENDAR_SCOPES)
    service = build("calendar", "v3", credentials=credentials)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return events_result.get("items", [])


def list_events_for_day(day: date | None = None, max_results: int = 20) -> List[Dict]:
    selected_day = day or date.today()
    start_dt = datetime.combine(selected_day, time.min).astimezone()
    end_dt = start_dt + timedelta(days=1)
    return get_events_between(start_dt, end_dt, max_results=max_results)


def format_calendar_events(events: List[Dict], empty_message: str = "Nenhum evento encontrado.") -> str:
    if not events:
        return empty_message

    lines = []
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
        summary = event.get("summary", "(Sem titulo)")
        if end:
            lines.append(f"- {summary} | {start} ate {end}")
        else:
            lines.append(f"- {summary} | {start}")
    return "\n".join(lines)


def create_calendar_event(
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    description: str | None = None,
    location: str | None = None,
    attendees: List[str] | None = None,
) -> Dict:
    credentials = _get_credentials(CALENDAR_SCOPES)
    service = build("calendar", "v3", credentials=credentials)
    event = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": GOOGLE_CALENDAR_TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": GOOGLE_CALENDAR_TIMEZONE,
        },
    }
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]

    return service.events().insert(calendarId="primary", body=event).execute()


def get_document_metadata(document_id: str) -> str:
    doc = get_document_content(document_id)
    title = doc.get("title", "Sem título")
    paragraphs = doc.get("paragraphs", [])

    preview = "\n".join(paragraphs[:3])
    formatted_preview = preview if preview else "Pré-visualização não disponível."

    return f"*Documento:* {title}\n\n{formatted_preview}"


def _docs_service():
    credentials = _get_credentials(DOCS_SCOPES)
    return build("docs", "v1", credentials=credentials)


def get_document_content(document_id: str) -> Dict:
    service = _docs_service()
    doc = service.documents().get(documentId=document_id).execute()
    title = doc.get("title", "Sem título")
    content_elements: List[Dict] = doc.get("body", {}).get("content", [])
    paragraphs: List[str] = []

    for element in content_elements:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text_runs = [
            run.get("textRun", {}).get("content", "")
            for run in paragraph.get("elements", [])
        ]
        combined = "".join(text_runs).strip()
        if combined:
            paragraphs.append(combined)

    return {
        "id": document_id,
        "title": title,
        "paragraphs": paragraphs,
        "text": "\n\n".join(paragraphs),
    }
