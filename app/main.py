from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.stations import LineName, STATIONS, Station, find_stations, get_station_by_id
from app.trenitalia import SearchCriteria, SolutionRequest, search_day_solutions, search_solutions


app = FastAPI(title="API Trenitalia Palermo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StationRouteRequest(BaseModel):
    from_station_id: int = Field(alias="fromStationId")
    to_station_id: int = Field(alias="toStationId")
    departure_time: datetime = Field(alias="departureTime")
    adults: int = 1
    children: int = 0
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    best_fare: bool = Field(default=False, alias="bestFare")


class DaySolutionsRequest(BaseModel):
    from_station_id: int = Field(alias="fromStationId")
    to_station_id: int = Field(alias="toStationId")
    date_: date = Field(alias="date")
    start_time: time = Field(default=time(0, 0), alias="startTime")
    adults: int = 1
    children: int = 0
    regional_only: bool = Field(default=True, alias="regionalOnly")
    no_changes: bool = Field(default=False, alias="noChanges")
    order: str = "DEPARTURE_DATE"
    page_size: int = Field(default=10, ge=1, le=10, alias="pageSize")
    max_pages: int = Field(default=12, ge=1, le=24, alias="maxPages")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations", response_model=list[Station])
def stations(
    q: str | None = Query(default=None, description="Search by station name or alias"),
    line: LineName | None = Query(default=None),
) -> list[Station]:
    return find_stations(q, line)


@app.get("/stations/{station_id}", response_model=Station)
def station(station_id: int) -> Station:
    result = get_station_by_id(station_id)
    if not result:
        raise HTTPException(status_code=404, detail="Station not found")
    return result


@app.get("/lines")
def lines() -> dict[str, list[Station]]:
    return {
        "palermo_punta_raisi": [station for station in STATIONS if station.line == "palermo_punta_raisi"],
        "palermo_cefalu": [station for station in STATIONS if station.line == "palermo_cefalu"],
        "extra": [station for station in STATIONS if station.line == "extra"],
    }


@app.post("/solutions")
async def solutions(request: StationRouteRequest) -> dict:
    if not get_station_by_id(request.from_station_id):
        raise HTTPException(status_code=400, detail="fromStationId is not in the curated station list")
    if not get_station_by_id(request.to_station_id):
        raise HTTPException(status_code=400, detail="toStationId is not in the curated station list")

    trenitalia_request = SolutionRequest(
        departureLocationId=request.from_station_id,
        arrivalLocationId=request.to_station_id,
        departureTime=request.departure_time,
        adults=request.adults,
        children=request.children,
        criteria=request.criteria,
        bestFare=request.best_fare,
    )
    return await search_solutions(trenitalia_request)


@app.post("/day-solutions")
async def day_solutions(request: DaySolutionsRequest) -> dict:
    from_station = get_station_by_id(request.from_station_id)
    to_station = get_station_by_id(request.to_station_id)
    if not from_station:
        raise HTTPException(status_code=400, detail="fromStationId is not in the curated station list")
    if not to_station:
        raise HTTPException(status_code=400, detail="toStationId is not in the curated station list")

    departure_time = datetime.combine(
        request.date_,
        request.start_time,
        tzinfo=ZoneInfo("Europe/Rome"),
    )
    criteria = SearchCriteria(
        frecceOnly=False,
        regionalOnly=request.regional_only,
        noChanges=request.no_changes,
        order=request.order,
        limit=request.page_size,
        offset=0,
    )
    trenitalia_request = SolutionRequest(
        departureLocationId=request.from_station_id,
        arrivalLocationId=request.to_station_id,
        departureTime=departure_time,
        adults=request.adults,
        children=request.children,
        criteria=criteria,
        bestFare=False,
    )
    result = await search_day_solutions(
        trenitalia_request,
        page_size=request.page_size,
        max_pages=request.max_pages,
    )
    result["fromStation"] = from_station.model_dump()
    result["toStation"] = to_station.model_dump()
    return result
