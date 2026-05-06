from __future__ import annotations

import os
from datetime import date as Date
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from app.stations import STATIONS, LineName, find_stations, get_station_by_id
from app.trenitalia import SearchCriteria, SolutionRequest, search_day_solutions, search_solutions


ALLOWED_STATION_IDS = sorted({station.id for station in STATIONS})
ALLOWED_STATIONS_TEXT = "\n".join(
    f"- {station.id}: {station.name} ({station.line})" for station in STATIONS
)

mcp = FastMCP(
    "trenitalia-palermo",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", os.getenv("MCP_PORT", "8000"))),
    instructions=(
        "Use this MCP only for the curated Trenitalia stations agreed with the user. "
        "Do not search arbitrary Italian stations. Allowed station IDs are:\n"
        f"{ALLOWED_STATIONS_TEXT}\n"
        "Conversation workflow: when the user asks for a train search, collect origin station, "
        "destination station, travel date, and the time they want to search from. If any of these "
        "are missing, ask for the missing field before calling a search tool. For local Palermo "
        "routes, prefer regional_only=true. Search tools return only SALEABLE trains and clean "
        "agent-facing fields."
    ),
)


def _station_to_dict(station) -> dict[str, Any]:
    return {
        "id": station.id,
        "name": station.name,
        "line": station.line,
        "aliases": station.aliases,
    }


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
    from_station: Any,
    to_station: Any,
    requested_from: str,
) -> dict[str, Any]:
    clean_solutions = [
        _clean_solution(solution)
        for solution in result.get("solutions", [])
        if solution.get("status") == "SALEABLE"
    ]
    return {
        "fromStation": {"id": from_station.id, "name": from_station.name},
        "toStation": {"id": to_station.id, "name": to_station.name},
        "requestedFrom": requested_from,
        "count": len(clean_solutions),
        "solutions": clean_solutions,
        "message": (
            "No hay trenes disponibles para comprar desde ese horario."
            if not clean_solutions
            else None
        ),
    }


@mcp.tool()
def list_allowed_stations(line: LineName | None = None) -> dict[str, Any]:
    """List the only Trenitalia station IDs this MCP is allowed to use.

    Allowed lines:
    - palermo_punta_raisi
    - palermo_cefalu
    - extra
    """
    stations = [station for station in STATIONS if line is None or station.line == line]
    return {
        "allowedStationIds": sorted({station.id for station in stations}),
        "stations": [_station_to_dict(station) for station in stations],
    }


@mcp.tool()
def find_allowed_station(query: str, line: LineName | None = None) -> dict[str, Any]:
    """Find station IDs by name or alias, limited to the curated station list."""
    matches = find_stations(query=query, line=line)
    return {
        "query": query,
        "line": line,
        "count": len(matches),
        "matches": [_station_to_dict(station) for station in matches],
        "allowedStationIds": ALLOWED_STATION_IDS,
    }


@mcp.tool()
async def search_trenitalia_solutions(
    from_station_id: int,
    to_station_id: int,
    departure_time: str,
    adults: int = 1,
    children: int = 0,
    regional_only: bool = True,
    no_changes: bool = False,
    order: Literal["DEPARTURE_DATE", "ARRIVAL_DATE", "FASTEST", "CHEAPEST"] = "DEPARTURE_DATE",
    limit: int = 10,
    offset: int = 0,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Search live Trenitalia solutions between allowed station IDs only.

    Conversation rule: before using this tool, make sure the user provided origin,
    destination, date, and desired start time. This tool returns only SALEABLE trains
    with clean fields for agent replies.

    Use only these IDs:
    830012002 Palermo Centrale
    830012134 Palermo Notarbartolo
    830012135 Palermo Vespri
    830012143 Palermo Lolli
    830012065 Palermo De Gasperi
    830012140 Palermo Francia
    830012130 Palermo Palazzo Reale-Orleans
    830012132 Palermo S. Lorenzo
    830012139 Palermo Cardillo-Zen
    830012069 Palermo La Malfa
    830012131 Palermo Tommaso Natale
    830012066 Palermo Sferracavallo
    830012129 Isola Delle Femmine
    830012128 Capaci
    830012126 Cinisi-Terrasini
    830012127 Carini
    830012133 Palermo Aeroporto / Punta Raisi
    830012055 Palermo Brancaccio
    830012032 Palermo Roccella
    830012035 Ficarazzi
    830012008 Bagheria
    830012009 S. Flavia-Solunto-Porticello
    830012010 Casteldaccia
    830012011 Altavilla Milicia
    830012012 S. Nicola (tonnara)
    830012013 Trabia
    830012014 Termini Imerese
    830012017 Campofelice
    830012018 Lascari
    830012019 Cefalu
    830012332 Catania Centrale
    830012216 Agrigento Centrale
    """
    from_station = get_station_by_id(from_station_id)
    to_station = get_station_by_id(to_station_id)
    if from_station is None:
        return {
            "error": "from_station_id is not allowed",
            "allowedStationIds": ALLOWED_STATION_IDS,
        }
    if to_station is None:
        return {
            "error": "to_station_id is not allowed",
            "allowedStationIds": ALLOWED_STATION_IDS,
        }

    criteria = SearchCriteria(
        frecceOnly=False,
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
    clean_result = _clean_saleable_response(
        result=result,
        from_station=from_station,
        to_station=to_station,
        requested_from=departure_time,
    )
    if include_raw:
        clean_result["raw"] = result.get("raw")
    return clean_result


@mcp.tool()
async def search_trenitalia_day_solutions(
    from_station_id: int,
    to_station_id: int,
    date: str,
    start_time: str,
    adults: int = 1,
    children: int = 0,
    regional_only: bool = True,
    no_changes: bool = False,
    page_size: int = 10,
    max_pages: int = 12,
) -> dict[str, Any]:
    """Return all same-day solutions from a user-selected start time onward.

    Conversation rule: before using this tool, make sure the user provided origin,
    destination, date, and desired start time. If the user did not say a start time,
    ask "A partir de que horario quieres la busqueda?" before calling this tool.
    Examples: start_time="18:00" returns only available departures at or after 18:00,
    such as 18:12 onward.
    """
    from_station = get_station_by_id(from_station_id)
    to_station = get_station_by_id(to_station_id)
    if from_station is None:
        return {
            "error": "from_station_id is not allowed",
            "allowedStationIds": ALLOWED_STATION_IDS,
        }
    if to_station is None:
        return {
            "error": "to_station_id is not allowed",
            "allowedStationIds": ALLOWED_STATION_IDS,
        }

    parsed_date = Date.fromisoformat(date)
    parsed_time = time.fromisoformat(start_time)
    departure_time = datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo("Europe/Rome"))
    criteria = SearchCriteria(
        frecceOnly=False,
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
        from_station=from_station,
        to_station=to_station,
        requested_from=departure_time.isoformat(),
    )


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT must be stdio, sse, or streamable-http")
    mcp.run(transport=transport)
