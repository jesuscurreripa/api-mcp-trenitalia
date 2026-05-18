from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.trenitalia import (
    SearchCriteria,
    SolutionRequest,
    Station,
    close_client,
    search_day_solutions,
    search_locations,
    search_solutions,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(
    title="API-MCP Trenitalia",
    description=(
        "API REST per la ricerca di treni, disponibilità e prezzi sulla rete ferroviaria italiana. "
        "Proxy verso lefrecce.it. Solo lettura: nessuna prenotazione, nessun acquisto."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

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
    include_raw: bool = Field(default=False, alias="includeRaw")


class DaySolutionsRequest(BaseModel):
    from_station_id: int = Field(alias="fromStationId")
    to_station_id: int = Field(alias="toStationId")
    date_: date = Field(alias="date")
    start_time: time = Field(default=time(0, 0), alias="startTime")
    adults: int = 1
    children: int = 0
    regional_only: bool = Field(default=False, alias="regionalOnly")
    frecce_only: bool = Field(default=False, alias="frecceOnly")
    no_changes: bool = Field(default=False, alias="noChanges")
    order: str = "DEPARTURE_DATE"
    page_size: int = Field(default=10, ge=1, le=10, alias="pageSize")
    max_pages: int = Field(default=12, ge=1, le=24, alias="maxPages")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations", response_model=list[Station])
async def stations(
    q: str = Query(..., min_length=2, description="Nome (parziale) della stazione, es. 'roma', 'milano centrale'"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[Station]:
    """Cerca stazioni italiane via lefrecce.it (autocompletamento)."""
    return await search_locations(q, limit=limit)


@app.post("/solutions")
async def solutions(request: StationRouteRequest) -> dict:
    trenitalia_request = SolutionRequest(
        departureLocationId=request.from_station_id,
        arrivalLocationId=request.to_station_id,
        departureTime=request.departure_time,
        adults=request.adults,
        children=request.children,
        criteria=request.criteria,
        bestFare=request.best_fare,
    )
    return await search_solutions(trenitalia_request, include_raw=request.include_raw)


@app.post("/day-solutions")
async def day_solutions(request: DaySolutionsRequest) -> dict:
    departure_time = datetime.combine(
        request.date_,
        request.start_time,
        tzinfo=ZoneInfo("Europe/Rome"),
    )
    criteria = SearchCriteria(
        frecceOnly=request.frecce_only,
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
    return await search_day_solutions(
        trenitalia_request,
        page_size=request.page_size,
        max_pages=request.max_pages,
    )
