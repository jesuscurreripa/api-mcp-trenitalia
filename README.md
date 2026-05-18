# API-MCP Trenitalia

**API REST + server MCP per la ricerca treni Trenitalia / lefrecce.it**

[![Licenza](https://img.shields.io/badge/Licenza-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![MCP](https://img.shields.io/badge/MCP-1.27-purple.svg)](https://modelcontextprotocol.io/)

Servizio REST e server **MCP (Model Context Protocol)** per la **ricerca di treni, disponibilità e prezzi** sulla rete ferroviaria italiana. Fa da proxy verso il backend pubblico di [lefrecce.it](https://www.lefrecce.it/), esponendo endpoint puliti via [FastAPI](https://fastapi.tiangolo.com/) per applicazioni web/mobile e tool conversazionali via MCP per agenti AI (Claude, ecc.).

> [!IMPORTANT]
> **Scope: solo lettura.** Questo servizio è esclusivamente per **ricerca, disponibilità e prezzi**. **Non** effettua prenotazioni, **non** acquista biglietti, **non** gestisce carrelli, pagamenti, profili utente o e-ticket. Per acquistare un biglietto l'utente deve andare su [lefrecce.it](https://www.lefrecce.it/) o sull'app Trenitalia.

> **Disclaimer legale** — Questo progetto è uno strumento indipendente e **non** è affiliato, approvato o supportato da Trenitalia S.p.A., Ferrovie dello Stato Italiane, Italo o lefrecce.it. L'utente è l'unico responsabile del rispetto dei termini di servizio del portale lefrecce.it e della normativa vigente. L'uso programmatico del backend potrebbe violare i termini d'uso del servizio. Usalo a tuo rischio e per scopi leciti.

> [!NOTE]
> Non è richiesta alcuna registrazione né API key: lefrecce.it espone un BFF (Backend-For-Frontend) pubblico che questo servizio interroga via HTTP. Tutta la logica (paginazione, filtraggio, sanitizzazione) avviene lato server.

---

## Indice

- [Panoramica](#panoramica)
- [Architettura](#architettura)
- [Prerequisiti](#prerequisiti)
- [Avvio rapido](#avvio-rapido)
- [Configurazione](#configurazione)
- [Endpoint REST](#endpoint-rest)
  - [Health check](#health-check)
  - [Ricerca stazioni](#ricerca-stazioni)
  - [Soluzioni puntuali](#soluzioni-puntuali)
  - [Soluzioni del giorno](#soluzioni-del-giorno)
- [Server MCP](#server-mcp)
- [Esempi d'uso](#esempi-duso)
- [Deploy su Railway](#deploy-su-railway)
- [Dettagli tecnici](#dettagli-tecnici)
- [Risoluzione dei problemi](#risoluzione-dei-problemi)
- [Sviluppo](#sviluppo)
- [Ringraziamenti](#ringraziamenti)
- [Licenza](#licenza)

---

## Panoramica

L'API espone tre operazioni fondamentali — **tutte di sola lettura** — accessibili sia via REST che via MCP:

| Operazione | REST | Tool MCP | Descrizione |
|------------|------|----------|-------------|
| **Ricerca stazione** | `GET /stations?q=...` | `search_stations` | Autocompletamento sulle stazioni italiane |
| **Soluzioni puntuali** | `POST /solutions` | `search_trenitalia_solutions` | Una pagina di soluzioni da un orario preciso, con prezzi |
| **Soluzioni del giorno** | `POST /day-solutions` | `search_trenitalia_day_solutions` | Tutte le soluzioni del giorno dall'ora indicata, con prezzi |

Tutte le ricerche delegano al BFF di lefrecce.it (`Channels.Website.BFF.WEB/website`). Le risposte vengono normalizzate e ripulite prima di essere restituite al client.

### Cosa NON fa questo servizio

Per chiarezza, **fuori scope**:

- ❌ Prenotazione o acquisto di biglietti
- ❌ Gestione carrelli, sessioni utente, login Trenitalia/lefrecce
- ❌ Pagamenti, integrazione Stripe/PayPal, gestione fatture
- ❌ Emissione, download o invio di e-ticket / PDF
- ❌ Gestione posto a sedere, classe, supplementi, tariffe loyalty (CartaFRECCIA)
- ❌ Modifica/rimborso di biglietti già acquistati
- ❌ Real-time status del treno (ritardi, binario di partenza in stazione)

Per tutto quanto sopra, l'utente finale deve usare i canali ufficiali Trenitalia.

### Funzionalità principali

- **Copertura totale della rete italiana** — nessuna whitelist: le stazioni vengono cercate live tramite l'autocompletamento di lefrecce. Funziona per Roma, Milano, Palermo, Bolzano, qualsiasi fermata regionale.
- **REST + MCP nello stesso codice base** — il modulo `trenitalia.py` è condiviso: una sola implementazione, due interfacce.
- **Risoluzione CORS** — il backend chiama lefrecce per conto del client browser, eliminando i problemi di Same-Origin tipici delle chiamate dirette da frontend.
- **Paginazione automatica** — `day-solutions` itera le pagine del BFF, deduplica per ID, taglia automaticamente quando si passa al giorno successivo.
- **Filtri configurabili** — solo regionali, solo Frecce, senza cambi, ordinamento per partenza/arrivo/durata/prezzo.
- **Risposte MCP "pulite"** — i tool per agenti AI restituiscono solo treni `SALEABLE` (acquistabili) e nascondono i campi rumorosi del BFF.
- **Connessione HTTP riutilizzata** — `httpx.AsyncClient` globale gestito via FastAPI lifespan: una sola connessione TCP per più richieste.
- **Errori upstream propagati** — i 4xx/5xx di lefrecce vengono trasformati in `HTTPException` con status e body utile invece di 500 opachi.

### Limitazioni note

- **Nessun endpoint "lista completa stazioni"**: lefrecce non lo espone, quindi le ricerche sono per nome (minimo 2 caratteri). Cerca per città o per il nome esatto della fermata.
- **Nessun endpoint "stazione per ID"**: una stazione si recupera solo via ricerca testuale. Se conosci già l'ID, lo passi direttamente a `/solutions`.
- **Limiti del BFF**: lefrecce restituisce massimo 10 risultati per pagina e tipicamente massimo ~24 pagine per intervallo di giornata. `day-solutions` rispetta questi limiti (page_size ≤ 10, max_pages ≤ 24).
- **Risultati `NOT_SALEABLE`**: la REST li include (con campo `status`); il MCP li filtra in modo che l'agente non li proponga all'utente.
- **Nessuna cache**: ogni richiesta colpisce lefrecce. Per traffico alto valuta di mettere un layer di cache davanti (Redis, edge cache).

---

## Architettura

```
┌──────────────────┐     ┌──────────────────┐
│ Browser / App    │     │  Agente AI       │
│ (HTTP / JSON)    │     │  (Claude, ecc.)  │
└────────┬─────────┘     └────────┬─────────┘
         │ REST                   │ MCP (stdio | SSE | streamable-http)
         ▼                        ▼
┌────────────────────┐   ┌──────────────────────────┐
│  FastAPI           │   │  FastMCP                 │
│  app/main.py       │   │  app/mcp_server.py       │
│   • /stations      │   │   • search_stations      │
│   • /solutions     │   │   • search_..._solutions │
│   • /day-solutions │   │   • search_..._day_..    │
└────────┬───────────┘   └────────────┬─────────────┘
         │                            │
         └────────────┬───────────────┘
                      ▼
         ┌────────────────────────────┐
         │  app/trenitalia.py         │
         │   • Station / Search...    │
         │     / SolutionRequest      │
         │   • get_client() (httpx)   │
         │   • search_locations()     │
         │   • search_solutions()     │
         │   • search_day_solutions() │
         └────────────┬───────────────┘
                      │ httpx (async, keep-alive)
                      ▼
         ┌────────────────────────────┐
         │  lefrecce.it BFF           │
         │  /locations/search         │
         │  /ticket/solutions         │
         └────────────────────────────┘
```

### File del progetto

| File | Descrizione |
|------|-------------|
| `app/main.py` | App FastAPI: endpoint REST, modelli Pydantic di input, CORS, lifespan |
| `app/trenitalia.py` | Client lefrecce.it: modelli (`Station`, `SearchCriteria`, `SolutionRequest`), `httpx.AsyncClient` globale, funzioni di ricerca, paginazione `day-solutions` |
| `app/mcp_server.py` | Server MCP (FastMCP) con tool `search_stations`, `search_trenitalia_solutions`, `search_trenitalia_day_solutions` |
| `app/__init__.py` | Marker pacchetto |
| `requirements.txt` | Dipendenze Python pinnate |
| `railway.json` | Comando di start per il servizio REST su Railway |
| `railway.mcp.json` | Esempio di config Railway per il servizio MCP |

---

## Prerequisiti

- **Python 3.11+** (uso di `from __future__ import annotations`, `ZoneInfo`, `Literal`, generics nativi)
- **Connessione di rete** verso `https://www.lefrecce.it`
- Nessuna API key, nessuna registrazione

Per il deploy:

- Account [Railway](https://railway.app/) (o qualsiasi PaaS che supporti Python + variabili `$PORT`)

---

## Avvio rapido

### Installazione locale

```bash
git clone <questo-repo>
cd API-MCP-Trenitalia

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Servizio attivo su:

- `http://127.0.0.1:8000/docs` — Swagger UI
- `http://127.0.0.1:8000/health` — health check

### Server MCP locale (stdio)

```bash
.venv/bin/python -m app.mcp_server
```

Configurazione di esempio per Claude Desktop o altri client MCP:

```json
{
  "mcpServers": {
    "api-mcp-trenitalia": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/API-MCP-Trenitalia"
    }
  }
}
```

---

## Configurazione

Nessuna configurazione obbligatoria per la modalità REST. Per il server MCP sono disponibili variabili d'ambiente opzionali:

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Trasporto MCP: `stdio`, `sse` o `streamable-http` |
| `MCP_HOST` | `127.0.0.1` | Host di bind per trasporti HTTP |
| `PORT` | `8000` | Porta di bind (Railway la inietta automaticamente) |
| `MCP_PORT` | `8000` | Alias di `PORT` se quest'ultima non è impostata |

---

## Endpoint REST

### Health check

```
GET /health
```

```json
{ "status": "ok" }
```

---

### Ricerca stazioni

```
GET /stations?q=<nome>&limit=<n>
```

Autocompletamento sulle stazioni italiane. Proxy verso `lefrecce.it/locations/search`.

**Query string:**

| Campo | Tipo | Obbligatorio | Default | Descrizione |
|-------|------|:------------:|---------|-------------|
| `q` | `string` | ✅ | — | Nome (anche parziale) della stazione, minimo 2 caratteri |
| `limit` | `int` | | `10` | Numero massimo di risultati (1–50) |

**Esempio:**

```bash
curl 'http://127.0.0.1:8000/stations?q=milano&limit=3'
```

**Risposta:**

```json
[
  {
    "id": 830001650,
    "name": "Milano ( Tutte Le Stazioni )",
    "displayName": "Milano ( Tutte Le Stazioni )",
    "timezone": "Europe/Rome",
    "multistation": true,
    "centroidId": 830001650
  },
  {
    "id": 830001700,
    "name": "Milano Centrale",
    "displayName": "Milano Centrale",
    "timezone": "Europe/Rome",
    "multistation": false,
    "centroidId": 830001650
  },
  {
    "id": 830001645,
    "name": "Milano Porta Garibaldi",
    "displayName": "Milano Porta Garibaldi",
    "timezone": "Europe/Rome",
    "multistation": false,
    "centroidId": 830001650
  }
]
```

> Le stazioni `multistation=true` sono "metastazioni" che includono tutti gli scali di una città. Sono valide come `from`/`to` in `/solutions`.

---

### Soluzioni puntuali

```
POST /solutions
```

Restituisce una pagina di soluzioni di viaggio a partire da un orario preciso.

**Request body:**

| Campo | Tipo | Obbligatorio | Default | Descrizione |
|-------|------|:------------:|---------|-------------|
| `fromStationId` | `int` | ✅ | — | ID stazione di partenza (da `/stations`) |
| `toStationId` | `int` | ✅ | — | ID stazione di arrivo |
| `departureTime` | `string` (ISO 8601) | ✅ | — | Orario di partenza con timezone, es. `2026-05-20T08:30:00+02:00` |
| `adults` | `int` | | `1` | Numero adulti (≥1) |
| `children` | `int` | | `0` | Numero bambini (≥0) |
| `criteria.frecceOnly` | `bool` | | `false` | Solo Frecce |
| `criteria.regionalOnly` | `bool` | | `false` | Solo regionali |
| `criteria.noChanges` | `bool` | | `false` | Solo viaggi diretti |
| `criteria.order` | `string` | | `DEPARTURE_DATE` | `DEPARTURE_DATE` \| `ARRIVAL_DATE` \| `FASTEST` \| `CHEAPEST` |
| `criteria.limit` | `int` | | `10` | Risultati per pagina (1–50, ma il BFF tipicamente ne dà max 10) |
| `criteria.offset` | `int` | | `0` | Offset per paginazione manuale |
| `bestFare` | `bool` | | `false` | Attiva la ricerca miglior tariffa |
| `includeRaw` | `bool` | | `false` | Include il payload originale del BFF nella risposta |

**Esempio:**

```bash
curl -X POST 'http://127.0.0.1:8000/solutions' \
  -H 'Content-Type: application/json' \
  -d '{
    "fromStationId": 830001700,
    "toStationId": 830008409,
    "departureTime": "2026-05-20T08:30:00+02:00",
    "adults": 1,
    "criteria": { "frecceOnly": true, "order": "FASTEST", "limit": 5 }
  }'
```

**Risposta (estratto):**

```json
{
  "searchId": "abc123...",
  "cartId": null,
  "count": 5,
  "solutions": [
    {
      "id": "...",
      "origin": "Milano Centrale",
      "destination": "Roma Termini",
      "departureTime": "2026-05-20T08:50:00",
      "arrivalTime": "2026-05-20T11:55:00",
      "duration": "3h 5m",
      "status": "SALEABLE",
      "price": 89.90,
      "currency": "EUR",
      "trains": [
        { "category": "FRECCIAROSSA", "acronym": "FR", "name": "9520" }
      ]
    }
  ]
}
```

---

### Soluzioni del giorno

```
POST /day-solutions
```

Recupera **tutte** le soluzioni del giorno a partire da un orario, paginando in automatico fino a esaurire la giornata.

**Request body:**

| Campo | Tipo | Obbligatorio | Default | Descrizione |
|-------|------|:------------:|---------|-------------|
| `fromStationId` | `int` | ✅ | — | ID stazione di partenza |
| `toStationId` | `int` | ✅ | — | ID stazione di arrivo |
| `date` | `string` | ✅ | — | Data `YYYY-MM-DD` |
| `startTime` | `string` | | `00:00` | Ora di partenza `HH:MM` (Europe/Rome) |
| `adults` | `int` | | `1` | Numero adulti |
| `children` | `int` | | `0` | Numero bambini |
| `regionalOnly` | `bool` | | `false` | Solo regionali |
| `frecceOnly` | `bool` | | `false` | Solo Frecce |
| `noChanges` | `bool` | | `false` | Solo viaggi diretti |
| `order` | `string` | | `DEPARTURE_DATE` | Ordinamento |
| `pageSize` | `int` | | `10` | Risultati per pagina (1–10) |
| `maxPages` | `int` | | `12` | Limite di pagine da scaricare (1–24) |

**Esempio:**

```bash
curl -X POST 'http://127.0.0.1:8000/day-solutions' \
  -H 'Content-Type: application/json' \
  -d '{
    "fromStationId": 830001700,
    "toStationId": 830008409,
    "date": "2026-05-20",
    "startTime": "18:00"
  }'
```

**Risposta (estratto):**

```json
{
  "from": "2026-05-20T18:00:00+02:00",
  "date": "2026-05-20",
  "pageSize": 10,
  "pagesFetched": 3,
  "count": 18,
  "solutions": [ ]
}
```

`pagesFetched` indica quante pagine sono state effettivamente richieste al BFF (si ferma prima di `maxPages` se si esaurisce la giornata o se una pagina è vuota).

---

## Server MCP

Il server MCP è implementato con [FastMCP](https://github.com/modelcontextprotocol/python-sdk) e riusa lo stesso modulo `trenitalia.py` degli endpoint REST.

### Tool disponibili

| Tool | Descrizione |
|------|-------------|
| `search_stations(query, limit)` | Autocompletamento stazioni — equivalente di `GET /stations` |
| `search_trenitalia_solutions(from_station_id, to_station_id, departure_time, ...)` | Soluzioni puntuali — equivalente di `POST /solutions` ma filtra solo `SALEABLE` |
| `search_trenitalia_day_solutions(from_station_id, to_station_id, date, start_time, ...)` | Soluzioni del giorno — equivalente di `POST /day-solutions` ma filtra solo `SALEABLE` |

### Comportamento agente raccomandato

L'`instructions` del server impone esplicitamente che l'agente raccolga **quattro dati** prima di chiamare una ricerca di treni:

1. Stazione di partenza
2. Stazione di arrivo
3. Data di viaggio
4. Ora di partenza (da quando cercare)

Se uno di questi manca, l'agente deve chiederlo all'utente **prima** di invocare il tool.

### Risposte MCP pulite

A differenza degli endpoint REST, i tool MCP:

- Rimuovono i campi rumorosi del BFF (`searchId`, `cartId`, `origin`/`destination` ridondanti, raw JSON).
- Filtrano fuori i treni con `status != "SALEABLE"`, in modo che l'agente non proponga all'utente treni non acquistabili.
- Restituiscono i treni come stringhe compatte (`"FR 9520"`) invece di oggetti annidati.
- Includono un campo `message` in italiano se la lista risultante è vuota.

### Trasporti supportati

| Trasporto | Quando usarlo |
|-----------|---------------|
| `stdio` (default) | Client locali (Claude Desktop, IDE plugin) che lanciano il processo on-demand |
| `streamable-http` | Server MCP remoto su Railway/altri PaaS, endpoint `/mcp` |
| `sse` | Compatibilità con vecchi client basati su Server-Sent Events |

Imposta `MCP_TRANSPORT=streamable-http` per la modalità remota.

---

## Esempi d'uso

### Flusso completo con cURL

```bash
# 1. Trova la stazione di partenza
curl -s 'http://127.0.0.1:8000/stations?q=palermo%20centrale&limit=3' | jq .

# 2. Trova la stazione di arrivo
curl -s 'http://127.0.0.1:8000/stations?q=catania&limit=3' | jq .

# 3. Cerca tutte le soluzioni del giorno dalle 14:00
curl -s -X POST 'http://127.0.0.1:8000/day-solutions' \
  -H 'Content-Type: application/json' \
  -d '{
    "fromStationId": 830012002,
    "toStationId": 830012332,
    "date": "2026-05-20",
    "startTime": "14:00"
  }' | jq '.solutions[] | {dep:.departureTime, arr:.arrivalTime, price, trains:.trains[].acronym}'
```

### Client Python

```python
import httpx
from datetime import date

BASE = "http://127.0.0.1:8000"

with httpx.Client(base_url=BASE, timeout=30.0) as c:
    # 1. Risolvi le stazioni per nome
    origine = c.get("/stations", params={"q": "milano centrale", "limit": 1}).json()[0]
    arrivo = c.get("/stations", params={"q": "roma termini", "limit": 1}).json()[0]

    # 2. Cerca tutte le soluzioni del giorno
    r = c.post("/day-solutions", json={
        "fromStationId": origine["id"],
        "toStationId": arrivo["id"],
        "date": str(date.today()),
        "startTime": "07:00",
        "frecceOnly": True,
    }).json()

    print(f"Trovate {r['count']} soluzioni in {r['pagesFetched']} pagine")
    for s in r["solutions"][:5]:
        trains = ", ".join(f"{t['acronym']} {t['name']}" for t in s["trains"])
        print(f"  {s['departureTime']} → {s['arrivalTime']}  €{s['price']}  [{trains}]")
```

---

## Deploy su Railway

### Servizio REST

Il file `railway.json` contiene il comando di start di produzione:

```json
{
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

Procedura:

1. Crea un nuovo progetto Railway dal repo GitHub.
2. Railway rileva `requirements.txt` e fa il build automatico.
3. Vai su **Settings → Networking** e genera un dominio pubblico.
4. Verifica: `https://<tuo-dominio>/health`, `/docs`, `/stations?q=roma`.

Non committare `.venv` o `.env` (sono già in `.gitignore`).

### Servizio MCP remoto

Per un MCP raggiungibile via HTTP da agenti remoti, crea un **secondo servizio Railway** dallo stesso repo e imposta il comando di start:

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 python -m app.mcp_server
```

Railway fornisce `$PORT` automaticamente. L'endpoint MCP sarà:

```
https://<tuo-dominio-mcp>/mcp
```

Il file `railway.mcp.json` è una config di esempio: impostala dalla dashboard Railway oppure copiala in `railway.json` su un branch dedicato.

---

## Dettagli tecnici

### Client HTTP riutilizzato

Un singolo `httpx.AsyncClient` viene creato a livello di modulo via `get_client()` e chiuso nel `lifespan` di FastAPI:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()
```

Vantaggi: connessioni TCP keep-alive, pool di connessioni, niente handshake TLS a ogni richiesta. Sotto carico la differenza è significativa.

### Paginazione `day-solutions`

L'algoritmo (`app/trenitalia.py`):

1. Imposta `offset=0`, `limit=page_size` (default 10).
2. Chiama `/ticket/solutions` ripetutamente, incrementando l'`offset`.
3. Per ogni risultato:
   - Se `departureTime` è **oltre** la data target → marca `reached_next_day` e scarta.
   - Se è **prima** dello `start_time` richiesto → scarta.
   - Se l'ID è già stato visto → scarta (deduplica).
   - Altrimenti → aggiungi alla lista.
4. Interrompi se: `reached_next_day=True`, pagina vuota, pagina sotto `page_size`, o `max_pages` raggiunto.

In pratica per una giornata tipica con treni ogni 10–30 minuti, servono 2–6 pagine.

### Gestione errori upstream

`_request()` traduce sempre gli errori lefrecce in `HTTPException`:

| Condizione | Status restituito | Body |
|------------|-------------------|------|
| `httpx.RequestError` (DNS, TCP, TLS, timeout) | `502` | `"Errore di rete verso lefrecce.it: <dettagli>"` |
| Lefrecce risponde 4xx/5xx | Stesso status | `"Errore da lefrecce.it: <primi 200 char del body>"` |

Niente `500 Internal Server Error` opachi per problemi che vengono dall'upstream.

### Modelli Pydantic v2

Tutti i modelli usano `populate_by_name=True` (implicito tramite `Field(alias=...)` per accettare sia il nome italiano/camelCase del JSON sia il nome Python snake_case nelle costruzioni interne. Esempio:

```python
SolutionRequest(departureLocationId=830001700, ...)   # da JSON / API
SolutionRequest(departure_location_id=830001700, ...) # da codice Python
```

### Trasformazione delle date

`startTime` di `/day-solutions` viene combinato con `date` usando `zoneinfo.ZoneInfo("Europe/Rome")`, in modo che `"18:00"` significhi sempre le 18:00 ora italiana indipendentemente dal fuso del server.

I `departureTime` ricevuti da lefrecce sono parsati con `datetime.fromisoformat` (sostituendo eventuali `Z` finali per compatibilità Python <3.11).

---

## Risoluzione dei problemi

| Problema | Causa probabile | Soluzione |
|----------|-----------------|----------|
| `GET /stations` restituisce `[]` | Query troppo corta o nome non riconosciuto da lefrecce | Prova con almeno 2–3 caratteri; usa il nome esatto della città (es. `roma` invece di `rm`) |
| `502 Bad Gateway` dalla nostra API | Lefrecce è down o l'IP del server è bloccato | Verifica con `curl https://www.lefrecce.it` dal server |
| `POST /solutions` restituisce `count: 0` | Nessun treno disponibile per i criteri scelti | Allarga: rimuovi `frecceOnly`/`regionalOnly`, prova un orario più ampio |
| `day-solutions` molto lento | Stai scaricando molte pagine | Riduci `maxPages`, stringi la finestra alzando `startTime` |
| MCP non si avvia | Trasporto non valido | `MCP_TRANSPORT` deve essere `stdio`, `sse` o `streamable-http` |
| Agente AI cerca stazioni inesistenti | Allucinazioni LLM | Le `instructions` del server richiedono di passare per `search_stations`. Verifica che il client MCP carichi le instructions |
| CORS error nel browser | Stai chiamando lefrecce.it direttamente, non questo proxy | Punta il frontend a `http://tuo-server:8000`, non a `lefrecce.it` |

Per debug, esponi i log uvicorn (`--log-level debug`) e/o aggiungi `includeRaw: true` a `/solutions` per ispezionare la risposta originale del BFF.

---

## Sviluppo

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Struttura del codice

**`app/trenitalia.py`** — cuore del progetto:

- `Station`, `SearchCriteria`, `SolutionRequest` — modelli Pydantic
- `get_client()` / `close_client()` — lifecycle del client HTTP
- `_request(method, path, **kwargs)` — wrapper unificato con gestione errori
- `search_locations(name, limit)` — autocompletamento stazioni
- `search_solutions(request, include_raw)` — ricerca singola pagina
- `search_day_solutions(request, page_size, max_pages, include_raw)` — paginazione + filtro giornata
- `summarize_solution(item)` — normalizza un risultato BFF nel nostro shape

**`app/main.py`** — strato HTTP:

- Lifespan FastAPI per chiudere il client httpx
- `StationRouteRequest`, `DaySolutionsRequest` — input model con alias camelCase
- Endpoint `/health`, `/stations`, `/solutions`, `/day-solutions`

**`app/mcp_server.py`** — strato MCP:

- Istanza `FastMCP` con `instructions` in italiano
- Tre `@mcp.tool()` async che delegano a `trenitalia.py`
- `_clean_solution()` / `_clean_saleable_response()` — sanitizzazione output

### Convenzioni

- Italiano per i messaggi utente-facing, gli `instructions` MCP e la documentazione.
- Inglese per identificatori, nomi di endpoint e nomi di funzioni (standard).
- Niente commenti banali: il codice spiega cosa fa, i commenti spiegano solo *perché*.
- Pydantic v2 ovunque, niente dict non tipizzati ai bordi.

### Test rapido senza framework

```bash
python3 -c "
import asyncio
from app.trenitalia import search_locations, close_client
async def main():
    stations = await search_locations('roma', limit=3)
    for s in stations:
        print(s.id, s.name)
    await close_client()
asyncio.run(main())
"
```

---

## Ringraziamenti

Questo progetto è partito studiando e prendendo ispirazione da due lavori precedenti della community che hanno fatto reverse-engineering del backend di lefrecce.it. Senza di loro avrei dovuto ricostruire da zero la mappatura degli endpoint e dei payload del BFF — un grazie sincero:

- **[TrinTragula/api-trenitalia](https://github.com/TrinTragula/api-trenitalia)** — implementazione di riferimento di un proxy verso lefrecce.it. Mi ha aiutato a capire la struttura del payload di `POST /ticket/solutions` (`departureLocationId`, `arrivalLocationId`, `criteria`, `advancedSearchRequest.bestFare`) e gli ordinamenti supportati (`DEPARTURE_DATE`, `ARRIVAL_DATE`, `FASTEST`, `CHEAPEST`).
- **[SimoDax/Trenitalia-API — Wiki](https://github.com/SimoDax/Trenitalia-API/wiki/API-Trenitalia---lefrecce.it)** — documentazione community degli endpoint pubblici di lefrecce.it e dei vari stati di una soluzione (`SALEABLE`, `NOT_SALEABLE`, ecc.). Punto di partenza essenziale per capire cosa filtrare quando si lavora con un agente AI.

Le scelte implementative di questo progetto (architettura REST+MCP condivisa, paginazione `day-solutions`, sanitizzazione lato MCP, gestione errori upstream) sono originali, ma il debito iniziale verso questi due lavori è importante e va riconosciuto.

Se hai contribuito a uno dei due progetti e vuoi essere citato esplicitamente nel commit history o in questa sezione, apri pure una issue.

---

## Licenza

Distribuito sotto licenza **[GNU Affero General Public License v3.0 — only](LICENSE)** (`SPDX-License-Identifier: AGPL-3.0-only`).

### ⚠️ Stai forkando? Leggi prima questa sezione

AGPL-3.0 è una **strong copyleft network license**. La clausola §13 ("Remote Network Interaction") impone obblighi che molti sviluppatori sottovalutano. Se intendi forkare `API-MCP-Trenitalia` e usarlo in un servizio di rete (es. un'app, una dashboard, un'API B2B, un agente AI che esponi a utenti finali), sei tenuto a:

1. **Mantenere AGPL-3.0** in tutte le distribuzioni del fork. Non puoi rilicenziare ad Apache, MIT, BSD, GPL-2, GPL-3 o altre licenze.
2. **Preservare** il file `LICENSE`, gli header SPDX e i credit all'autore originale in ogni copia distribuita o ridistribuita.
3. **Pubblicare le tue modifiche** al codice sotto AGPL-3.0, includendo l'intera storia git delle modifiche.
4. **Se esponi il fork (o un suo derivato) come servizio di rete** — SaaS, API pubblica, agente MCP remoto, microservizio interno raggiungibile da utenti esterni — devi offrire a tutti gli utenti del servizio l'accesso pubblico al *Corresponding Source* completo dell'opera combinata, comprese:
   - le tue modifiche al codice base,
   - **tutte le componenti private linkate o combinate** col servizio (autenticazione, frontend, theme, orchestratori, layer di cache, integrazioni Stripe/Clerk/CRM, schema DB e migrations, Dockerfile, Helm chart, IaC),
   - le installation information necessarie a ricostruire un deploy comparabile.
5. **Pubblicare un avviso visibile** ("prominent offer") nell'UI o nella documentazione API del servizio, con il link al Corresponding Source.

La mancata conformità ad AGPL §13 termina automaticamente i tuoi diritti sul software (AGPL §8).

### Checklist forker (rapida)

- [ ] Il `LICENSE` del mio fork è ancora `AGPL-3.0-only`?
- [ ] Gli header SPDX nei file sorgente sono preservati?
- [ ] Il `README` del mio fork attribuisce esplicitamente il progetto upstream?
- [ ] Tutte le dipendenze private che linkero/combinerò sono pronte a essere pubblicate come Corresponding Source, in caso di deploy in rete?
- [ ] Ho preparato la "prominent offer" del Corresponding Source nell'UI/docs del mio servizio?

### Perché AGPL e non MIT/Apache

L'obiettivo è impedire che qualcuno prenda questo proxy, lo metti dietro a un paywall come SaaS chiuso, e si tenga per sé le migliorie. Chi lo usa internamente per progetti personali, chi lo studia, chi contribuisce miglioramenti pubblici → non viene toccato dalla licenza. Chi lo trasforma in un prodotto commerciale di rete → deve restituire il codice alla community.

Se l'AGPL non si adatta al tuo caso d'uso (es. integrazione in piattaforma enterprise senza obbligo di pubblicare i moduli combinati), apri una issue per discutere una licenza commerciale separata.

---

*Ultimo aggiornamento: maggio 2026*
