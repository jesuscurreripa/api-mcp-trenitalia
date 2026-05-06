# API Trenitalia Palermo

FastAPI proxy for a curated list of Trenitalia stations:

- Palermo-Punta Raisi / Trinacria Express
- Palermo-Cefalu regional line
- Catania Centrale and Agrigento Centrale

The service avoids browser CORS problems by calling `lefrecce.it` from the backend.

## Run

```bash
cd "/Users/jesuscurreri/Desktop/api trenitalia"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/stations`
- `http://127.0.0.1:8000/lines`

## Example

Search Palermo Centrale to Palermo Aeroporto:

```bash
curl -X POST 'http://127.0.0.1:8000/solutions' \
  -H 'Content-Type: application/json' \
  --data '{
    "fromStationId": 830012002,
    "toStationId": 830012133,
    "departureTime": "2026-05-06T10:30:00+02:00",
    "adults": 1,
    "children": 0,
    "criteria": {
      "frecceOnly": false,
      "regionalOnly": true,
      "noChanges": false,
      "order": "DEPARTURE_DATE",
      "limit": 10,
      "offset": 0
    }
  }'
```

## MCP server

This project also includes an MCP server for AI agents. It exposes only the curated station IDs and rejects arbitrary station IDs.

Run it with stdio:

```bash
cd "/Users/jesuscurreri/Desktop/api trenitalia"
.venv/bin/python -m app.mcp_server
```

Example MCP config:

```json
{
  "mcpServers": {
    "trenitalia-palermo": {
      "command": "/Users/jesuscurreri/Desktop/api trenitalia/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/Users/jesuscurreri/Desktop/api trenitalia"
    }
  }
}
```

Available MCP tools:

- `list_allowed_stations`
- `find_allowed_station`
- `search_trenitalia_solutions`
- `search_trenitalia_day_solutions`

See `API_EXPLICACION.txt` and `MCP_EXPLICACION.txt` for the Spanish explanation files.

MCP behavior for agents:

- Ask for origin, destination, date, and desired start time before searching.
- Use only the curated station IDs.
- Search responses include only `SALEABLE` trains.
- `NOT_SALEABLE` trains are hidden from agent-facing results.

## Railway deploy

### API service

The repo includes `railway.json` with the production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway injects `$PORT` automatically. After deploying from GitHub, generate a public domain in Railway's Networking settings and check:

- `/health`
- `/docs`
- `/stations`
- `/day-solutions`

Do not commit `.venv` or `.env`; both are ignored.

### MCP service

The default MCP mode is `stdio`, for local agents that launch a command. For a remote Railway MCP service, create a second Railway service from the same repo and use this start command:

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 python -m app.mcp_server
```

Railway will provide `$PORT`; the MCP server reads it automatically. The MCP endpoint is:

```text
/mcp
```

There is also a `railway.mcp.json` example. Railway normally reads `railway.json`, so for the MCP service either set the start command in the Railway dashboard or copy the MCP config into `railway.json` on a separate branch/service.
