# TransitGPT Canada

A conversational AI web app that lets you ask plain-English questions about Canadian public transit — agencies, routes, stops, schedules, directions, maps, charts, and PDF reports — powered by a real national transit database and live Google Maps data.

---

## What It Does

Type a question like:

- *"What bus routes does the TTC have?"*
- *"Show TTC subway stations on a map"*
- *"How do I get from Barrie Railway Station to Johnson at Mayor?"*
- *"Show a pie chart of route types across Canada"*
- *"Generate a PDF report of all transit agencies in Ontario"*

The app queries a PostgreSQL database loaded with GTFS data from transit agencies across every Canadian province and territory, combines it with live Google Maps directions, and returns a clear, readable answer.

---

## Features

- **Natural language to SQL** — ask questions in plain English, the AI writes and runs the SQL
- **Directions across all travel modes** — transit (step-by-step), car, and walking, narrated conversationally
- **Live Google Maps** — interactive maps with stop markers rendered directly in the browser
- **Chart.js charts** — bar and pie charts generated from live database queries
- **PDF report generation** — downloadable agency/route reports built with ReportLab
- **Fuzzy name matching** — FAISS vector search finds the right agency even with typos or informal names
- **Conversation memory** — remembers the last 3 exchanges so follow-up questions work naturally
- **Transit terminology disambiguation** — understands "GO train", "subway", "streetcar", "SeaBus", "intercity bus", and more

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, Chart.js, Google Maps JavaScript API |
| Backend | Python, Flask |
| AI Agent | LangChain ReAct agent, GPT-4o-mini (OpenAI) |
| Vector Search | FAISS + OpenAI Embeddings |
| Database | PostgreSQL |
| Maps & Directions | Google Maps Platform (Geocoding, Directions, Places APIs) |
| Data Format | GTFS (General Transit Feed Specification) |

---

## Project Structure

```
app/
├── server.py          # Flask web server and session management
├── main.py            # AI agent setup and question processing
├── prefix.py          # System prompt and instructions for the AI
├── boilerplate.py     # Reusable SQL and JavaScript templates
├── tools.py           # Custom tools: geocoding, directions, vector search
├── ingest.py          # One-time GTFS data loader into PostgreSQL
├── requirements.txt   # Python dependencies
└── templates/
    └── index.html     # Frontend UI
```

The `gtfs/` folder (one level up) holds the raw GTFS feeds from Statistics Canada and is not committed — see Data Source below.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/marianami19/transitgpt.git
cd canadian_public_transit_network_database
```

### 2. Create a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in this folder:

```
OPENAI_API_KEY=your_openai_api_key
GPLACES_API_KEY=your_google_maps_api_key
PG_USER=your_postgres_username
PG_PASSWORD=your_postgres_password
PG_PORT=5432
TRANSIT_PG_DB=transit_gpt
FLASK_SECRET=any_random_secret_string
```

### 4. Set up the database

In PostgreSQL, create the database:

```sql
CREATE DATABASE transit_gpt;
GRANT ALL PRIVILEGES ON DATABASE transit_gpt TO your_user;
\c transit_gpt
GRANT ALL ON SCHEMA public TO your_user;
```

### 5. Download the GTFS data

Download the Canadian Public Transit Network Database from Statistics Canada:

> Statistics Canada. (2025). *Canadian Public Transit Network Database*.
> https://www150.statcan.gc.ca/n1/pub/23-26-0003/232600032025001-eng.htm

Extract the GTFS feeds into a `gtfs/` folder **one level above this folder** (i.e. alongside `app/`), with one subfolder per agency — the folder name becomes the `custom_id` in the database.

### 6. Load the data

```bash
python ingest.py
```

Reads all GTFS files and loads agencies, routes, stops, trips, and calendar into PostgreSQL. Run once.

### 7. Run the app

```bash
python server.py
```

Open your browser at `http://localhost:5000`.

---

## APIs Required

You will need API keys from:

- **OpenAI** — for GPT-4o-mini and embeddings: https://platform.openai.com
- **Google Maps Platform** — enable Geocoding API, Directions API, Places API, and Maps JavaScript API: https://console.cloud.google.com

---

## Data Source

Transit data sourced from:

> Statistics Canada. (2025). *Canadian Public Transit Network Database*. Statistics Canada Catalogue no. 23-26-0003.
> https://www150.statcan.gc.ca/n1/pub/23-26-0003/232600032025001-eng.htm

Data is provided in GTFS format and covers transit agencies across all Canadian provinces and territories.

---

## How It Works

```
User question (browser)
        │
        ▼
Flask server (server.py)
        │
        ▼
LangChain ReAct Agent (main.py)
  ├── Writes & runs SQL queries against PostgreSQL
  ├── Calls Google Maps geocoding (address → coordinates)
  ├── Calls Google Maps directions (step-by-step transit/driving/walking)
  ├── Calls Google Places (nearby locations)
  └── Searches agency/route names via FAISS vector index
        │
        ▼
Response post-processing (main.py)
  ├── Markdown text → rendered HTML
  ├── ```html blocks → live maps and charts injected into page
  └── ```python blocks → executed server-side to generate PDFs
        │
        ▼
Browser renders the answer
```

---

