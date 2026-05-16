import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from bot.google_maps import (
    geocode_address,
    get_directions,
    get_place_details,
    search_places,
)
from bot.google_services import (
    create_calendar_event,
    get_document_content,
    get_drive_file_metadata,
    get_drive_files,
    get_email_metadata,
    get_events_between,
    get_recent_emails,
    list_events_for_day,
)


load_dotenv()

mcp = FastMCP(
    "RaizitoBot Google MCP",
    instructions=(
        "Ferramentas MCP para acessar Google Calendar, Maps, Drive, Docs e Gmail "
        "com as credenciais configuradas no ambiente do RaizitoBot."
    ),
    json_response=True,
)


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value).astimezone()
    except ValueError as exc:
        raise ValueError("Use datetime ISO 8601, ex: 2026-05-14T09:00:00-03:00") from exc


def _split_attendees(attendees: str | None) -> list[str]:
    if not attendees:
        return []
    return [item.strip() for item in attendees.split(",") if item.strip()]


@mcp.tool()
def gmail_list_recent(query: str | None = None, max_results: int = 10) -> list[dict[str, Any]]:
    """List recent Gmail messages, optionally filtered with Gmail search syntax."""
    return get_recent_emails(query=query, max_results=max(1, min(max_results, 25)))


@mcp.tool()
def gmail_get_metadata(message_id: str) -> dict[str, Any]:
    """Get Gmail metadata and snippet for a message id."""
    return get_email_metadata(message_id)


@mcp.tool()
def drive_search_files(query: str | None = None, page_size: int = 10) -> list[dict[str, Any]]:
    """Search Google Drive files by name or list recent files when query is empty."""
    return get_drive_files(query=query, page_size=max(1, min(page_size, 25)))


@mcp.tool()
def drive_get_file_metadata(file_id: str) -> dict[str, Any]:
    """Get metadata for a Google Drive file."""
    return get_drive_file_metadata(file_id)


@mcp.tool()
def docs_get_document(document_id: str) -> dict[str, Any]:
    """Read title and text content from a Google Docs document."""
    return get_document_content(document_id)


@mcp.tool()
def calendar_list_today(max_results: int = 20) -> list[dict[str, Any]]:
    """List Google Calendar events for today."""
    return list_events_for_day(max_results=max(1, min(max_results, 50)))


@mcp.tool()
def calendar_list_between(start_iso: str, end_iso: str, max_results: int = 20) -> list[dict[str, Any]]:
    """List Google Calendar events between two ISO 8601 datetimes."""
    return get_events_between(
        _parse_datetime(start_iso),
        _parse_datetime(end_iso),
        max_results=max(1, min(max_results, 50)),
    )


@mcp.tool()
def calendar_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
    attendees_csv: str | None = None,
) -> dict[str, Any]:
    """Create a Google Calendar event. Datetimes must be ISO 8601 with timezone."""
    return create_calendar_event(
        summary=summary,
        start_dt=_parse_datetime(start_iso),
        end_dt=_parse_datetime(end_iso),
        description=description,
        location=location,
        attendees=_split_attendees(attendees_csv),
    )


@mcp.tool()
def maps_geocode(address: str, region: str | None = "br") -> dict[str, Any]:
    """Geocode an address using Google Maps Geocoding API."""
    return geocode_address(address, region=region)


@mcp.tool()
def maps_search_places(
    query: str,
    location: str | None = None,
    radius: int | None = None,
) -> dict[str, Any]:
    """Search places with Google Maps Places Text Search."""
    return search_places(query=query, location=location, radius=radius)


@mcp.tool()
def maps_get_place_details(place_id: str) -> dict[str, Any]:
    """Get details for a Google Maps place id."""
    return get_place_details(place_id)


@mcp.tool()
def maps_get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
    departure_time: str | None = None,
) -> dict[str, Any]:
    """Get directions between two addresses or coordinates."""
    return get_directions(
        origin=origin,
        destination=destination,
        mode=mode,
        departure_time=departure_time,
    )


def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
