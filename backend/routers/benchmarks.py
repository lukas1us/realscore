"""
POST /api/benchmarks/refresh — manually recompute price benchmarks from properties table.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.benchmarks import refresh_benchmarks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["benchmarks"])


@router.post("/benchmarks/refresh")
def refresh(db: Session = Depends(get_db)):
    """Recompute all price benchmarks from current properties data."""
    total = refresh_benchmarks(db)
    return {"status": "ok", "rows": total}
