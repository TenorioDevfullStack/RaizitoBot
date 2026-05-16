import os
from typing import Any

import requests


MAPS_API_BASE = "https://maps.googleapis.com/maps/api"


def _maps_api_key() -> str:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY is not configured.")
    return api_key


def _get_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    request_params = {key: value for key, value in params.items() if value not in (None, "")}
    request_params["key"] = _maps_api_key()
    response = requests.get(f"{MAPS_API_BASE}/{path}", params=request_params, timeout=30)
    response.raise_for_status()
    data = response.json()
    status = data.get("status")
    if status and status not in {"OK", "ZERO_RESULTS"}:
        message = data.get("error_message") or status
        raise ValueError(f"Google Maps API error: {message}")
    return data


def geocode_address(address: str, region: str | None = None, language: str | None = None) -> dict[str, Any]:
    data = _get_json(
        "geocode/json",
        {
            "address": address,
            "region": region,
            "language": language or os.getenv("GOOGLE_MAPS_LANGUAGE", "pt-BR"),
        },
    )
    results = data.get("results", [])
    return {
        "status": data.get("status"),
        "results": [
            {
                "formatted_address": item.get("formatted_address"),
                "place_id": item.get("place_id"),
                "location": item.get("geometry", {}).get("location"),
                "types": item.get("types", []),
            }
            for item in results
        ],
    }


def search_places(
    query: str,
    location: str | None = None,
    radius: int | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    data = _get_json(
        "place/textsearch/json",
        {
            "query": query,
            "location": location,
            "radius": radius,
            "language": language or os.getenv("GOOGLE_MAPS_LANGUAGE", "pt-BR"),
        },
    )
    return {
        "status": data.get("status"),
        "results": [
            {
                "name": item.get("name"),
                "formatted_address": item.get("formatted_address"),
                "place_id": item.get("place_id"),
                "rating": item.get("rating"),
                "user_ratings_total": item.get("user_ratings_total"),
                "location": item.get("geometry", {}).get("location"),
                "opening_hours": item.get("opening_hours"),
            }
            for item in data.get("results", [])
        ],
    }


def get_place_details(place_id: str, language: str | None = None) -> dict[str, Any]:
    fields = (
        "place_id,name,formatted_address,formatted_phone_number,website,"
        "rating,user_ratings_total,geometry,opening_hours,url"
    )
    data = _get_json(
        "place/details/json",
        {
            "place_id": place_id,
            "fields": fields,
            "language": language or os.getenv("GOOGLE_MAPS_LANGUAGE", "pt-BR"),
        },
    )
    return {
        "status": data.get("status"),
        "result": data.get("result", {}),
    }


def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
    language: str | None = None,
    departure_time: str | None = None,
) -> dict[str, Any]:
    data = _get_json(
        "directions/json",
        {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "language": language or os.getenv("GOOGLE_MAPS_LANGUAGE", "pt-BR"),
            "departure_time": departure_time,
        },
    )
    routes = []
    for route in data.get("routes", []):
        legs = route.get("legs", [])
        routes.append(
            {
                "summary": route.get("summary"),
                "warnings": route.get("warnings", []),
                "legs": [
                    {
                        "start_address": leg.get("start_address"),
                        "end_address": leg.get("end_address"),
                        "distance": leg.get("distance"),
                        "duration": leg.get("duration"),
                        "duration_in_traffic": leg.get("duration_in_traffic"),
                    }
                    for leg in legs
                ],
            }
        )
    return {
        "status": data.get("status"),
        "routes": routes,
    }
