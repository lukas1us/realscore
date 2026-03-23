import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import analysis, properties, batch, benchmarks

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _migrate_db()
    yield


app = FastAPI(
    title="RealScore CZ API",
    description="Czech real estate investment scoring tool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(properties.router)
app.include_router(batch.router)
app.include_router(benchmarks.router)


def _migrate_db():
    """Apply additive schema changes that create_all cannot handle on existing tables."""
    from sqlalchemy import text
    from backend.database import engine
    migrations = [
        "ALTER TABLE properties ADD COLUMN IF NOT EXISTS has_elevator BOOLEAN",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))
        conn.commit()


@app.get("/health")
def health():
    return {"status": "ok"}
