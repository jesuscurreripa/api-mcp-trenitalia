from __future__ import annotations

import os
from datetime import date as Date
from datetime import datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from app.trenitalia import (
    SearchCriteria,
    SolutionRequest,
    search_day_solutions,
    search_locations,
    search_solutions,
)


mcp = FastMCP(
    "api-mcp-trenitalia",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", os.getenv("MCP_PORT", "8000"))),
    instructions=(
        "MCP per la ricerca di treni, disponibilita' e prezzi sulla rete "
        "ferroviaria italiana (Trenitalia / lefrecce.it).\n\n"
        "SCOPE: SOLO LETTURA. Questo server non effettua prenotazioni, non acquista "
        "biglietti, non gestisce carrelli o pagamenti. Se l'utente vuole comprare un "
        "biglietto, indirizzalo a lefrecce.it o all'app Trenitalia.\n\n"
        "Flusso conversazionale obbligatorio: prima di chiamare una ricerca di treni, "
        "raccogli sempre dall'utente: stazione di partenza, stazione di arrivo, data, "
        "e ora a partire dalla quale cercare. Se manca uno di questi dati, chiedilo "
        "prima di chiamare il tool.\n\n"
        "Per ottenere gli ID delle stazioni usa search_stations (es. 'roma', 'milano centrale'). "
        "Le ricerche restituiscono solo treni SALEABLE (acquistabili al momento) con campi essenziali."
    ),
)


def _clean_solution(solution: dict[str, Any]) -> dict[str, Any]:
    trains = [
        " ".join(part for part in [train.get("acronym"), train.get("name")] if part)
        for train in solution.get("trains", [])
    ]
    return {
        "departureTime": solution.get("departureTime"),
        "arrivalTime": solution.get("arrivalTime"),
        "duration": solution.get("duration"),
        "price": solution.get("price"),
        "currency": solution.get("currency"),
        "trains": trains,
    }


def _clean_saleable_response(
    *,
    result: dict[str, Any],
    from_station_id: int,
    to_station_id: int,
    requested_from: str,
) -> dict[str, Any]:
    clean_solutions = [
        _clean_solution(solution)
        for solution in result.get("solutions", [])
        if solution.get("status") == "SALEABLE"
    ]
    return {
        "fromStationId": from_station_id,
        "toStationId": to_station_id,
        "requestedFrom": requested_from,
        "count": len(clean_solutions),
        "solutions": clean_solutions,
        "message": (
            "Nessun treno acquistabile trovato per quell'orario."
            if not clean_solutions
            else None
        ),
    }


@mcp.tool()
async def search_stations(query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca stazioni italiane per nome (autocompletamento lefrecce.it).

    Esempi: 'roma', 'milano centrale', 'palermo aeroporto', 'venezia santa lucia'.
    Restituisce gli ID stazione da usare in search_trenitalia_solutions.
    """
    stations = await search_locations(query, limit=limit)
    return {
        "query": query,
        "count": len(stations),
        "stations": [s.model_dump(by_alias=True) for s in stations],
    }


@mcp.tool()
async def search_trenitalia_solutions(
    from_station_id: int,
    to_station_id: int,
    departure_time: str,
    adults: int = 1,
    children: int = 0,
    regional_only: bool = False,
    frecce_only: bool = False,
    no_changes: bool = False,
    order: Literal["DEPARTURE_DATE", "ARRIVAL_DATE", "FASTEST", "CHEAPEST"] = "DEPARTURE_DATE",
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Cerca soluzioni di viaggio Trenitalia tra due stazioni.

    Parametri:
    - from_station_id, to_station_id: ottenuti da search_stations.
    - departure_time: ISO 8601 con timezone, es. '2026-05-20T08:30:00+02:00'.
    - regional_only=True per cercare solo treni regionali.
    - frecce_only=True per cercare solo Frecce.

    Restituisce solo treni SALEABLE (acquistabili).
    """
    criteria = SearchCriteria(
        frecceOnly=frecce_only,
        regionalOnly=regional_only,
        noChanges=no_changes,
        order=order,
        limit=limit,
        offset=offset,
    )
    request = SolutionRequest(
        departureLocationId=from_station_id,
        arrivalLocationId=to_station_id,
        departureTime=datetime.fromisoformat(departure_time),
        adults=adults,
        children=children,
        criteria=criteria,
        bestFare=False,
    )
    result = await search_solutions(request)
    return _clean_saleable_response(
        result=result,
        from_station_id=from_station_id,
        to_station_id=to_station_id,
        requested_from=departure_time,
    )


@mcp.tool()
async def search_trenitalia_day_solutions(
    from_station_id: int,
    to_station_id: int,
    date: str,
    start_time: str,
    adults: int = 1,
    children: int = 0,
    regional_only: bool = False,
    frecce_only: bool = False,
    no_changes: bool = False,
    page_size: int = 10,
    max_pages: int = 12,
) -> dict[str, Any]:
    """Restituisce tutte le soluzioni del giorno a partire dall'ora indicata.

    Parametri:
    - date: 'YYYY-MM-DD'.
    - start_time: 'HH:MM', es. '18:00' restituisce tutte le partenze dalle 18:00 in poi.

    Se l'utente non ha indicato un orario di partenza, chiedi:
    'A che ora vuoi iniziare la ricerca?' prima di chiamare questo tool.
    """
    parsed_date = Date.fromisoformat(date)
    parsed_time = time.fromisoformat(start_time)
    departure_time = datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo("Europe/Rome"))
    criteria = SearchCriteria(
        frecceOnly=frecce_only,
        regionalOnly=regional_only,
        noChanges=no_changes,
        order="DEPARTURE_DATE",
        limit=page_size,
        offset=0,
    )
    request = SolutionRequest(
        departureLocationId=from_station_id,
        arrivalLocationId=to_station_id,
        departureTime=departure_time,
        adults=adults,
        children=children,
        criteria=criteria,
        bestFare=False,
    )
    result = await search_day_solutions(request, page_size=page_size, max_pages=max_pages)
    return _clean_saleable_response(
        result=result,
        from_station_id=from_station_id,
        to_station_id=to_station_id,
        requested_from=departure_time.isoformat(),
    )


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT deve essere stdio, sse o streamable-http")
    mcp.run(transport=transport)
