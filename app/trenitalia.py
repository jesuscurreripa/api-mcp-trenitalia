from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field


BASE_URL = "https://www.lefrecce.it/Channels.Website.BFF.WEB/website"


class Station(BaseModel):
    id: int
    name: str
    display_name: str = Field(alias="displayName")
    timezone: str
    multistation: bool
    centroid_id: int | None = Field(default=None, alias="centroidId")

    model_config = {"populate_by_name": True}


class SearchCriteria(BaseModel):
    frecce_only: bool = Field(default=False, alias="frecceOnly")
    regional_only: bool = Field(default=False, alias="regionalOnly")
    no_changes: bool = Field(default=False, alias="noChanges")
    order: Literal["DEPARTURE_DATE", "ARRIVAL_DATE", "FASTEST", "CHEAPEST"] = "DEPARTURE_DATE"
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class SolutionRequest(BaseModel):
    departure_location_id: int = Field(alias="departureLocationId")
    arrival_location_id: int = Field(alias="arrivalLocationId")
    departure_time: datetime = Field(alias="departureTime")
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    best_fare: bool = Field(default=False, alias="bestFare")


_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE_URL, timeout=20.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    client = get_client()
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Errore di rete verso lefrecce.it: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Errore da lefrecce.it: {response.text[:200]}",
        )
    return response.json()


async def search_locations(name: str, limit: int = 10) -> list[Station]:
    """Cerca stazioni italiane tramite l'autocompletamento di lefrecce.it."""
    data = await _request("GET", "/locations/search", params={"name": name, "limit": limit})
    return [Station.model_validate(item) for item in data]


def _solution_payload(request: SolutionRequest) -> dict[str, Any]:
    return {
        "departureLocationId": request.departure_location_id,
        "arrivalLocationId": request.arrival_location_id,
        "departureTime": request.departure_time.isoformat(),
        "adults": request.adults,
        "children": request.children,
        "criteria": request.criteria.model_dump(by_alias=True),
        "advancedSearchRequest": {"bestFare": request.best_fare},
    }


def summarize_solution(item: dict[str, Any]) -> dict[str, Any]:
    solution = item.get("solution", {})
    price = solution.get("price") or {}
    trains = solution.get("trains") or []
    return {
        "id": solution.get("id"),
        "origin": solution.get("origin"),
        "destination": solution.get("destination"),
        "departureTime": solution.get("departureTime"),
        "arrivalTime": solution.get("arrivalTime"),
        "duration": solution.get("duration"),
        "status": solution.get("status"),
        "price": price.get("amount"),
        "currency": price.get("currency"),
        "trains": [
            {
                "category": train.get("trainCategory"),
                "acronym": train.get("acronym"),
                "name": train.get("name"),
            }
            for train in trains
        ],
    }


async def search_solutions(
    request: SolutionRequest, *, include_raw: bool = False
) -> dict[str, Any]:
    data = await _request(
        "POST",
        "/ticket/solutions",
        json=_solution_payload(request),
        headers={"Content-Type": "application/json"},
    )
    result = {
        "searchId": data.get("searchId"),
        "cartId": data.get("cartId"),
        "count": len(data.get("solutions") or []),
        "solutions": [summarize_solution(item) for item in data.get("solutions") or []],
    }
    if include_raw:
        result["raw"] = data
    return result


def _parse_trenitalia_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def search_day_solutions(
    request: SolutionRequest,
    *,
    page_size: int = 10,
    max_pages: int = 12,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Pagina i risultati di lefrecce e tiene solo le partenze del giorno richiesto, dall'ora indicata in poi."""
    start = request.departure_time
    target_date = start.date()
    offset = 0
    seen_ids: set[str] = set()
    solutions: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    page_count = 0

    for _ in range(max_pages):
        criteria = request.criteria.model_copy(update={"limit": page_size, "offset": offset})
        page_request = request.model_copy(update={"criteria": criteria})
        page = await search_solutions(page_request, include_raw=include_raw)
        page_count += 1
        page_solutions = page.get("solutions") or []
        if include_raw:
            raw_pages.append(page.get("raw") or {})
        if not page_solutions:
            break

        reached_next_day = False
        for solution in page_solutions:
            departure_value = solution.get("departureTime")
            if not departure_value:
                continue

            departure = _parse_trenitalia_datetime(departure_value)
            if departure.date() > target_date:
                reached_next_day = True
                continue
            if departure.date() != target_date or departure < start:
                continue

            solution_id = solution.get("id") or f"{departure_value}:{solution.get('arrivalTime')}"
            if solution_id in seen_ids:
                continue
            seen_ids.add(solution_id)
            solutions.append(solution)

        if reached_next_day or len(page_solutions) < page_size:
            break
        offset += page_size

    result = {
        "from": start.isoformat(),
        "date": target_date.isoformat(),
        "pageSize": page_size,
        "pagesFetched": page_count,
        "count": len(solutions),
        "solutions": solutions,
    }
    if include_raw:
        result["rawPages"] = raw_pages
    return result
