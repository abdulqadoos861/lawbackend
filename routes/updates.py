from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from db.database import get_db
from db.models import LawUpdate, Source

router = APIRouter()


@router.get("/updates")
def get_updates(
    search: Optional[str] = Query(None, description="Search by title keyword"),
    category: Optional[str] = Query(None, description="Filter by category: Bill, Act, Ordinance"),
    source_id: Optional[int] = Query(None, description="Filter by source ID"),
    date_from: Optional[date] = Query(None, description="Earliest date (YYYY-MM-DD) inclusive"),
    date_to: Optional[date] = Query(None, description="Latest date (YYYY-MM-DD) inclusive"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Results per page (max 200)"),
    db: Session = Depends(get_db),
):
    query = db.query(
        LawUpdate.id,
        LawUpdate.source_id,
        Source.name.label("source_name"),
        LawUpdate.title,
        LawUpdate.url,
        LawUpdate.pdf_url,
        LawUpdate.category,
        LawUpdate.date_found,
        LawUpdate.is_notified,
    ).join(Source, LawUpdate.source_id == Source.id)

    # Keyword search filter
    if search:
        query = query.filter(LawUpdate.title.ilike(f"%{search}%"))

    # Category filter
    if category:
        query = query.filter(LawUpdate.category == category)

    # Source filter
    if source_id:
        query = query.filter(LawUpdate.source_id == source_id)

    # Date range filters — convert date → datetime at start/end of day
    if date_from:
        query = query.filter(LawUpdate.date_found >= datetime(date_from.year, date_from.month, date_from.day, 0, 0, 0))
    if date_to:
        query = query.filter(LawUpdate.date_found <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59))

    # Sort descending by date
    total = query.count()
    offset = (page - 1) * limit
    results = query.order_by(LawUpdate.date_found.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "results": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "source_name": r.source_name,
                "title": r.title,
                "url": r.url,
                "pdf_url": r.pdf_url,
                "category": r.category,
                "date_found": r.date_found.isoformat() if r.date_found else None,
                "is_notified": r.is_notified,
            }
            for r in results
        ],
    }


@router.get("/updates/{update_id}")
def get_update(update_id: int, db: Session = Depends(get_db)):
    """Fetch a single law update by its ID."""
    row = (
        db.query(
            LawUpdate.id,
            LawUpdate.source_id,
            Source.name.label("source_name"),
            LawUpdate.title,
            LawUpdate.url,
            LawUpdate.pdf_url,
            LawUpdate.category,
            LawUpdate.date_found,
            LawUpdate.is_notified,
        )
        .join(Source, LawUpdate.source_id == Source.id)
        .filter(LawUpdate.id == update_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No law update found with ID {update_id}.",
        )
    return {
        "id": row.id,
        "source_id": row.source_id,
        "source_name": row.source_name,
        "title": row.title,
        "url": row.url,
        "pdf_url": row.pdf_url,
        "category": row.category,
        "date_found": row.date_found.isoformat() if row.date_found else None,
        "is_notified": row.is_notified,
    }


@router.get("/sources")
def get_sources(db: Session = Depends(get_db)):
    """List all configured scraping sources with their status."""
    sources = db.query(Source).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "scraper_type": s.scraper_type,
            "is_active": s.is_active,
            "last_crawled": s.last_crawled.isoformat() if s.last_crawled else None,
        }
        for s in sources
    ]
