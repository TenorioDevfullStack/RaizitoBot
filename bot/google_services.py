import os
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
DOCS_SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _gmail_user_id():
    return os.getenv("GOOGLE_GMAIL_USER_ID", "me")


def _calendar_id():
    return os.getenv("GOOGLE_CALENDAR_ID", "primary")


def _get_credentials(scopes: List[str], use_delegation: bool | None = None):
    json_creds = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    delegated_user = os.getenv("GOOGLE_DELEGATED_USER")

    if json_creds:
        import json
        try:
            creds_dict = json.loads(json_creds)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=scopes
            )
        except json.JSONDecodeError as e:
             raise ValueError(f"⚠️ Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
    elif service_account_file and os.path.exists(service_account_file):
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=scopes
        )
    else:
        raise ValueError("⚠️ No valid Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE.")

    if use_delegation is None:
        use_delegation = _env_flag("GOOGLE_USE_DOMAIN_WIDE_DELEGATION", bool(delegated_user))

    if delegated_user and use_delegation:
        credentials = credentials.with_subject(delegated_user)

    return credentials


def _get_gmail_credentials():
    return _get_credentials(
        GMAIL_SCOPES,
        use_delegation=_env_flag("GOOGLE_GMAIL_USE_DELEGATION", bool(os.getenv("GOOGLE_DELEGATED_USER"))),
    )


def _get_drive_credentials():
    return _get_credentials(
        DRIVE_SCOPES,
        use_delegation=_env_flag("GOOGLE_DRIVE_USE_DELEGATION", False),
    )


def _get_calendar_credentials():
    return _get_credentials(
        CALENDAR_SCOPES,
        use_delegation=_env_flag("GOOGLE_CALENDAR_USE_DELEGATION", False),
    )


def _get_docs_credentials():
    return _get_credentials(
        DOCS_SCOPES,
        use_delegation=_env_flag("GOOGLE_DOCS_USE_DELEGATION", False),
    )


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
    credentials = _get_gmail_credentials()
    return build("gmail", "v1", credentials=credentials)


def _message_headers(message_detail: Dict) -> Dict:
    headers = message_detail.get("payload", {}).get("headers", [])
    return {header["name"].lower(): header.get("value", "") for header in headers}


def get_recent_emails(query: str | None = None, max_results: int = 10) -> List[Dict]:
    service = _gmail_service()
    response = (
        service.users()
        .messages()
        .list(userId=_gmail_user_id(), q=query or "", maxResults=max_results)
        .execute()
    )
    messages = response.get("messages", [])
    emails = []

    for message in messages:
        detail = (
            service.users()
            .messages()
            .get(
                userId=_gmail_user_id(),
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
            userId=_gmail_user_id(),
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
    credentials = _get_drive_credentials()
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
    credentials = _get_calendar_credentials()
    service = build("calendar", "v3", credentials=credentials)

    now = datetime.now(timezone.utc).isoformat()
    events_result = (
        service.events()
        .list(
            calendarId=_calendar_id(),
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
    credentials = _get_calendar_credentials()
    service = build("calendar", "v3", credentials=credentials)

    events_result = (
        service.events()
        .list(
            calendarId=_calendar_id(),
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
    credentials = _get_calendar_credentials()
    service = build("calendar", "v3", credentials=credentials)
    calendar_timezone = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Sao_Paulo")
    event = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": calendar_timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": calendar_timezone,
        },
    }
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]

    return service.events().insert(calendarId=_calendar_id(), body=event).execute()


def get_document_metadata(document_id: str) -> str:
    doc = get_document_content(document_id)
    title = doc.get("title", "Sem título")
    paragraphs = doc.get("paragraphs", [])

    preview = "\n".join(paragraphs[:3])
    formatted_preview = preview if preview else "Pré-visualização não disponível."

    return f"*Documento:* {title}\n\n{formatted_preview}"


def _docs_service():
    credentials = _get_docs_credentials()
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
