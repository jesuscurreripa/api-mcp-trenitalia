from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


LineName = Literal["palermo_punta_raisi", "palermo_cefalu", "extra"]


class Station(BaseModel):
    id: int
    name: str
    line: LineName
    aliases: list[str] = []


STATIONS: list[Station] = [
    Station(id=830012002, name="Palermo Centrale", line="palermo_punta_raisi", aliases=["palermo centrale"]),
    Station(id=830012134, name="Palermo Notarbartolo", line="palermo_punta_raisi"),
    Station(id=830012135, name="Palermo Vespri", line="palermo_punta_raisi"),
    Station(id=830012143, name="Palermo Lolli", line="palermo_punta_raisi"),
    Station(id=830012065, name="Palermo De Gasperi", line="palermo_punta_raisi"),
    Station(id=830012140, name="Palermo Francia", line="palermo_punta_raisi"),
    Station(
        id=830012130,
        name="Palermo Palazzo Reale-Orleans",
        line="palermo_punta_raisi",
        aliases=["palazzo reale-orleans", "palazzo reale orleans"],
    ),
    Station(
        id=830012132,
        name="Palermo S. Lorenzo",
        line="palermo_punta_raisi",
        aliases=["palermo san lorenzo colli", "san lorenzo colli"],
    ),
    Station(id=830012139, name="Palermo Cardillo-Zen", line="palermo_punta_raisi"),
    Station(id=830012069, name="Palermo La Malfa", line="palermo_punta_raisi"),
    Station(
        id=830012131,
        name="Palermo Tommaso Natale",
        line="palermo_punta_raisi",
        aliases=["tommaso natale"],
    ),
    Station(id=830012066, name="Palermo Sferracavallo", line="palermo_punta_raisi"),
    Station(
        id=830012129,
        name="Isola Delle Femmine",
        line="palermo_punta_raisi",
        aliases=["isola delle femmine station"],
    ),
    Station(id=830012128, name="Capaci", line="palermo_punta_raisi", aliases=["capaci station"]),
    Station(id=830012126, name="Cinisi-Terrasini", line="palermo_punta_raisi"),
    Station(id=830012127, name="Carini", line="palermo_punta_raisi"),
    Station(
        id=830012133,
        name="Palermo Aeroporto",
        line="palermo_punta_raisi",
        aliases=["punta raisi", "punta raisi aeroporto", "aeroporto palermo"],
    ),
    Station(id=830012002, name="Palermo Centrale", line="palermo_cefalu"),
    Station(id=830012055, name="Palermo Brancaccio", line="palermo_cefalu"),
    Station(id=830012032, name="Palermo Roccella", line="palermo_cefalu"),
    Station(id=830012035, name="Ficarazzi", line="palermo_cefalu"),
    Station(id=830012008, name="Bagheria", line="palermo_cefalu"),
    Station(
        id=830012009,
        name="S. Flavia-Solunto-Porticello",
        line="palermo_cefalu",
        aliases=["santa flavia-solunto-porticello", "santa flavia solunto porticello"],
    ),
    Station(id=830012010, name="Casteldaccia", line="palermo_cefalu"),
    Station(id=830012011, name="Altavilla Milicia", line="palermo_cefalu"),
    Station(
        id=830012012,
        name="S. Nicola (tonnara)",
        line="palermo_cefalu",
        aliases=["san nicola l'arena", "san nicola tonnara", "san nicola arena"],
    ),
    Station(id=830012013, name="Trabia", line="palermo_cefalu"),
    Station(id=830012014, name="Termini Imerese", line="palermo_cefalu"),
    Station(
        id=830012017,
        name="Campofelice",
        line="palermo_cefalu",
        aliases=["campofelice di roccella"],
    ),
    Station(id=830012018, name="Lascari", line="palermo_cefalu"),
    Station(id=830012019, name="Cefalu", line="palermo_cefalu", aliases=["cefalù"]),
    Station(id=830012332, name="Catania Centrale", line="extra"),
    Station(id=830012216, name="Agrigento Centrale", line="extra"),
]


def normalize(value: str) -> str:
    return value.strip().lower().replace("'", "").replace("ù", "u")


def get_station_by_id(station_id: int) -> Station | None:
    for station in STATIONS:
        if station.id == station_id:
            return station
    return None


def find_stations(query: str | None = None, line: LineName | None = None) -> list[Station]:
    results = STATIONS
    if line:
        results = [station for station in results if station.line == line]
    if not query:
        return results

    needle = normalize(query)
    return [
        station
        for station in results
        if needle in normalize(station.name)
        or any(needle in normalize(alias) for alias in station.aliases)
    ]
