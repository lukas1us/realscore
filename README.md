# RealScore CZ 🏠

Czech real estate investment scoring tool. Paste a Sreality or Bezrealitky listing URL and get a composite investment score with detailed breakdown.

## Architecture

```
realscoreCZ/
├── backend/
│   ├── main.py            # FastAPI app entry point
│   ├── config.py          # Settings (loaded from .env)
│   ├── database.py        # SQLAlchemy engine + session
│   ├── models.py          # ORM models (Property, PriceBenchmark)
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── database/
│   │   ├── 000_initialization.sql      # Complete schema for fresh installations
│   │   ├── 002_add_kraj.sql            # ADD COLUMN kraj + backfill (existing DB)
│   │   └── 003_price_benchmarks.sql    # CREATE TABLE price_benchmarks + bootstrap (existing DB)
│   ├── routers/
│   │   ├── analysis.py    # POST /api/analyze
│   │   ├── batch.py       # POST /api/batch-analyze
│   │   ├── benchmarks.py  # POST /api/benchmarks/refresh
│   │   └── properties.py  # GET/DELETE /api/properties
│   ├── scrapers/
│   │   ├── sreality.py         # Sreality detail JSON API scraper
│   │   ├── sreality_search.py  # Sreality search URL parser + paginator
│   │   ├── bezrealitky.py      # Bezrealitky HTML scraper
│   │   ├── idnes.py            # reality.idnes.cz HTML scraper
│   │   └── market.py           # Active listing counter (liquidity)
│   ├── jobs/
│   │   └── full_market_scan.py    # Bulk scrape all Sreality listings (threaded)
│   ├── scripts/
│   │   ├── backfill_ownership.py  # Backfill ownership + score_liquidity from raw_data
│   │   └── backfill_city.py       # Backfill city municipality from raw_data["locality"]
│   ├── services/
│   │   ├── benchmarks.py  # Price benchmark lookup + refresh
│   │   ├── czso.py        # ČSÚ population + economic data
│   │   └── scoring.py     # Scoring engine (all 5 dimensions)
│   └── utils/
│       └── regions.py     # CITY_TO_REGION mapping, extract_kraj()
├── frontend/
│   └── app.py             # Streamlit single-page app
├── tests/
│   ├── conftest.py        # pytest fixtures (test DB setup + teardown)
│   ├── test_scoring.py    # Unit tests — scoring engine pure functions
│   ├── test_regions.py    # Unit tests — extract_kraj() fallback chain
│   ├── test_benchmarks.py # Unit tests — _normalize_city()
│   └── test_db.py         # SQL smoke tests — ORM, filters, benchmarks
├── requirements.txt
├── .env.example
├── docker-compose.yml     # PostgreSQL in Docker
└── README.md
```

## Prerequisites

- Python 3.11+
- PostgreSQL 14+

## How to Run

```bash
# 1. Create and activate a virtual environment
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set DATABASE_URL and BACKEND_URL

# 4. Start PostgreSQL in Docker
docker compose up -d

# 5. Start the backend (auto-creates the properties table on first run)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 6. In a separate terminal, start the frontend
streamlit run frontend/app.py --server.port 8501
```

| Service | URL |
|---------|-----|
| Streamlit UI | http://localhost:8501 |
| FastAPI docs | http://localhost:8000/docs |

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/yourhandle/realscoreCZ
cd realscoreCZ
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql://your_user:your_password@localhost:5432/realscoreCZ
BACKEND_URL=http://localhost:8000
```

### 3. Create the database

```bash
psql -U postgres -c "CREATE DATABASE realscoreCZ;"
```

**Fresh installation** — run the initialization migration to create the complete schema:

```bash
psql $DATABASE_URL -f backend/database/000_initialization.sql
```

This replaces the need to run migrations 002 and 003 on a new database.

**Existing installation** — apply additive migrations instead:

```bash
psql $DATABASE_URL -f backend/database/002_add_kraj.sql
psql $DATABASE_URL -f backend/database/003_price_benchmarks.sql
```

Migration 002 adds the `kraj` column and backfills it. Migration 003 creates `price_benchmarks` and bootstraps it from existing properties.

### 4. Start the FastAPI backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

### 5. Start the Streamlit frontend

In a separate terminal:

```bash
BACKEND_URL=http://localhost:8000 streamlit run frontend/app.py --server.port 8501
```

Open: http://localhost:8501

## Usage

### URL mode
Paste a Sreality or Bezrealitky URL into the input field and click **Analyzovat**.

Supported URL formats:
- `https://www.sreality.cz/detail/prodej/byt/2+1/Praha/.../12345678`
- `https://www.bezrealitky.cz/nemovitosti-byty-domy/...`

### Manual mode
Switch to the **Ruční zadání** tab and fill in the property parameters directly.

### History
Switch to **Historie analýz** to see all previously scored properties, sortable by score, yield, price, or date.

## Scoring Model

| Dimension | Weight | Data Source |
|-----------|--------|-------------|
| Rental Yield (`score_yield`) | 10 % | Estimated rent vs. purchase price |
| Demographic / Locality (`score_demographic`) | 40 % | SVL risk, locality tier, city stigma, ČSÚ population data |
| Economic / Energy (`score_economic`) | 20 % | PENB energy class |
| Property Quality (`score_quality`) | 15 % | Construction type, floor, building age, revitalization |
| Liquidity / Ownership (`score_liquidity`) | 15 % | OV vs. DV ownership, active listings |

### Score interpretation

| Score | Label | Color |
|-------|-------|-------|
| 65–100 | Dobrá investice | Green |
| 40–64 | Průměrná investice | Amber |
| 0–39 | Riziková investice | Red |

Any dimension below 40 generates a **red flag** in the output.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/realscoreCZ` | PostgreSQL connection string |
| `BACKEND_URL` | `http://localhost:8000` | FastAPI base URL (used by Streamlit) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Analyze a property (URL or manual fields) |
| `POST` | `/api/batch-analyze` | Batch-analyze a Sreality search URL |
| `GET` | `/api/properties` | List analyzed properties (with filters + pagination) |
| `GET` | `/api/properties/filters` | Available filter options (regions, energy classes, …) |
| `GET` | `/api/properties/count` | Count properties matching filters |
| `GET` | `/api/properties/{id}` | Property detail with financial calculations + price benchmark |
| `DELETE` | `/api/properties/{id}` | Delete a property record |
| `DELETE` | `/api/properties` | Delete all property records |
| `POST` | `/api/benchmarks/refresh` | Recompute price benchmarks from current DB data |
| `GET` | `/health` | Health check |

### Example request

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.sreality.cz/detail/prodej/byt/2+1/Praha/.../12345678"
  }'
```

Or manual:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Brno",
    "district": "Brno-město",
    "price": 4500000,
    "size_m2": 65,
    "disposition": "2+1",
    "construction_type": "cihla",
    "energy_class": "C",
    "year_built": 1995
  }'
```

## Price Benchmarks

The property detail view shows **Cena vs. trh** — how the listing's price/m² compares to the market average for the same city and disposition type.

Benchmarks are computed by aggregating the existing properties database (no additional scraping). They are stored in the `price_benchmarks` table and must be initialized by running the migration:

```bash
psql $DATABASE_URL -f backend/database/003_price_benchmarks.sql
```

To refresh benchmarks after a large batch import:

```bash
curl -X POST http://localhost:8000/api/benchmarks/refresh
```

Lookup strategy: city + disposition → fallback to city-wide average (all types). Minimum sample size: 3 properties per group.

## Regions (Kraj)

Each property stores its Czech region (`kraj`) at insert time, derived from the city/district fields. This enables the **Filter dle kraje** in the history view. The mapping covers all 14 Czech regions via `backend/utils/regions.py`.

If kraj is missing for existing records, re-run migration 002:

```bash
psql $DATABASE_URL -f backend/database/002_add_kraj.sql
```

## Backfill Scripts

One-off scripts for fixing existing DB records after scraper improvements.

### Backfill city (`backfill_city.py`)

Re-extracts the municipality name into the `city` field from `raw_data["locality"]` for Sreality records. Needed because the original parser stored the street name in `city` instead of the actual municipality.

```bash
python -m backend.scripts.backfill_city --dry-run   # preview changes
python -m backend.scripts.backfill_city             # apply
```

Only processes Sreality records (others lack structured locality in `raw_data`). Does not modify the `district` field.

### Backfill ownership (`backfill_ownership.py`)

Fills in missing `ownership` (OV/DV) and recalculates `score_liquidity` + `score_total` for existing records:

```bash
python -m backend.scripts.backfill_ownership --dry-run
python -m backend.scripts.backfill_ownership
```

## Full Market Scan

`backend/jobs/full_market_scan.py` stáhne a ohodnotí všechny prodejní inzeráty bytů ze Sreality pro všechny kraje. Obchází limit ~1 000 výsledků API tak, že prostor hledání rozpadá na regiony (14 krajů) a dále na typy dispozic, pokud je kraj příliš velký.

```bash
# Základní spuštění (výchozí cenový strop 5 000 000 Kč)
python -m backend.jobs.full_market_scan

# Vlastní cenový strop
python -m backend.jobs.full_market_scan --price-max 3000000

# Dry-run — jen spočítá počet inzerátů, nepíše do DB
python -m backend.jobs.full_market_scan --dry-run

# Ladicí režim — jen jeden kraj (region ID 1–14)
python -m backend.jobs.full_market_scan --region 14
```

Výchozí nastavení:

| Parametr | Hodnota | Popis |
|----------|---------|-------|
| `--price-max` | 5 000 000 | Maximální cena v Kč |
| `ID_WORKERS` | 8 | Vlákna pro sběr ID z API |
| `SCRAPE_WORKERS` | 5 | Vlákna pro detail scraping + scoring |
| `COMMIT_BATCH` | 50 | Počet záznamů mezi DB commity |

Záznamy, které již v DB existují (detekce dle URL/estate ID), jsou přeskočeny — job je bezpečné spouštět opakovaně.

## Tests

The test suite has 136 tests across 4 files. Unit tests have no external dependencies; SQL smoke tests require a running PostgreSQL instance.

### Run unit tests only (no DB required)

```bash
pytest tests/test_scoring.py tests/test_regions.py tests/test_benchmarks.py -v
```

### Run the full suite (requires PostgreSQL)

The SQL smoke tests use a dedicated `realscoreCZ_test` database which is created automatically on first run.

```bash
pytest tests/ -v
```

By default, the test DB is expected at `postgresql://postgres:password@localhost:5432/realscoreCZ_test`. Override with the `TEST_DATABASE_URL` environment variable:

```bash
TEST_DATABASE_URL=postgresql://myuser:mypass@localhost:5432/realscoreCZ_test pytest tests/ -v
```

### Test coverage overview

| File | Tests | What it covers |
|------|-------|----------------|
| `test_scoring.py` | 77 | Score functions: SVL penalties, PENB, ownership, physical quality, yield curve, mortgage, financials, red flags, summary text |
| `test_regions.py` | 29 | `extract_kraj()` all 6 fallback steps + CITY_TO_REGION data integrity |
| `test_benchmarks.py` | 8 | `_normalize_city()` edge cases |
| `test_db.py` | 22 | ORM CRUD, filter queries, benchmark lookup + refresh idempotency |

## Notes

- **Sreality scraping**: uses the internal JSON API at `https://www.sreality.cz/api/cs/v2/estates/{id}` – no login required.
- **Bezrealitky scraping**: HTML scraping via BeautifulSoup (they block API access).
- **ČSÚ data**: fetched live from the public REST API and open-data CSV exports; results are cached in-process (LRU cache) per session.
- If scraping fails for any reason, the app falls back to the manually entered fields.
- All estimated rents are gross (before tax/management fees). For net yield calculations, subtract ~25–30%.
- **Deduplication**: re-submitting a URL that already exists in the DB returns the cached result without re-scraping.
