import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional
from db.database import get_db
from db.models import Admin, Source
from scraper.crawler import crawl_all_sources

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AdminCreateSchema(BaseModel):
    name: Optional[str] = "Admin Officer"
    email: EmailStr

class AdminResponseSchema(BaseModel):
    id: int
    name: Optional[str]
    email: str

    class Config:
        from_attributes = True


VALID_SCRAPER_TYPES = {"na", "senate", "molaw", "generic"}

class SourceCreateSchema(BaseModel):
    name: str
    url: str
    scraper_type: Optional[str] = "generic"
    is_active: Optional[bool] = True

class SourceUpdateSchema(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    scraper_type: Optional[str] = None
    is_active: Optional[bool] = None

class SourceResponseSchema(BaseModel):
    id: int
    name: str
    url: str
    scraper_type: str
    is_active: bool
    last_crawled: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Admin / Receiver Routes
# ---------------------------------------------------------------------------

@router.get("/receivers", response_model=List[AdminResponseSchema])
def get_receivers(db: Session = Depends(get_db)):
    return db.query(Admin).all()


@router.post("/receivers", response_model=AdminResponseSchema, status_code=status.HTTP_201_CREATED)
def add_receiver(payload: AdminCreateSchema, db: Session = Depends(get_db)):
    exists = db.query(Admin).filter(Admin.email == payload.email).first()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email address '{payload.email}' is already registered.",
        )
    new_admin = Admin(name=payload.name, email=payload.email)
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin


@router.delete("/receivers/{id}")
def delete_receiver(id: int, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.id == id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin with ID {id} not found.",
        )
    db.delete(admin)
    db.commit()
    return {"success": True, "message": f"Successfully deleted receiver: {admin.email}"}


# ---------------------------------------------------------------------------
# Source / Website Management Routes
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=List[SourceResponseSchema])
def list_sources(db: Session = Depends(get_db)):
    """Return all scraping sources with their active status."""
    sources = db.query(Source).order_by(Source.id).all()
    return [
        SourceResponseSchema(
            id=s.id,
            name=s.name,
            url=s.url,
            scraper_type=s.scraper_type,
            is_active=s.is_active,
            last_crawled=s.last_crawled.isoformat() if s.last_crawled else None,
        )
        for s in sources
    ]


@router.post("/sources", response_model=SourceResponseSchema, status_code=status.HTTP_201_CREATED)
def add_source(payload: SourceCreateSchema, db: Session = Depends(get_db)):
    """Register a new website as a scraping source."""
    if payload.scraper_type not in VALID_SCRAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scraper_type '{payload.scraper_type}'. Choose from: {sorted(VALID_SCRAPER_TYPES)}",
        )
    # Prevent duplicate URLs
    duplicate = db.query(Source).filter(Source.url == payload.url).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A source with URL '{payload.url}' already exists (ID {duplicate.id}).",
        )
    new_source = Source(
        name=payload.name,
        url=payload.url,
        scraper_type=payload.scraper_type,
        is_active=payload.is_active,
    )
    db.add(new_source)
    db.commit()
    db.refresh(new_source)
    return SourceResponseSchema(
        id=new_source.id,
        name=new_source.name,
        url=new_source.url,
        scraper_type=new_source.scraper_type,
        is_active=new_source.is_active,
        last_crawled=None,
    )


@router.patch("/sources/{source_id}", response_model=SourceResponseSchema)
def update_source(source_id: int, payload: SourceUpdateSchema, db: Session = Depends(get_db)):
    """Update name, URL, scraper type, or active status of an existing source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with ID {source_id} not found.",
        )
    if payload.scraper_type is not None and payload.scraper_type not in VALID_SCRAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scraper_type '{payload.scraper_type}'. Choose from: {sorted(VALID_SCRAPER_TYPES)}",
        )
    if payload.name is not None:
        source.name = payload.name
    if payload.url is not None:
        source.url = payload.url
    if payload.scraper_type is not None:
        source.scraper_type = payload.scraper_type
    if payload.is_active is not None:
        source.is_active = payload.is_active

    db.commit()
    db.refresh(source)
    return SourceResponseSchema(
        id=source.id,
        name=source.name,
        url=source.url,
        scraper_type=source.scraper_type,
        is_active=source.is_active,
        last_crawled=source.last_crawled.isoformat() if source.last_crawled else None,
    )


@router.post("/sources/{source_id}/toggle", response_model=SourceResponseSchema)
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    """Quickly enable or disable a scraping source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with ID {source_id} not found.",
        )
    source.is_active = not source.is_active
    db.commit()
    db.refresh(source)
    state = "enabled" if source.is_active else "disabled"
    return SourceResponseSchema(
        id=source.id,
        name=source.name,
        url=source.url,
        scraper_type=source.scraper_type,
        is_active=source.is_active,
        last_crawled=source.last_crawled.isoformat() if source.last_crawled else None,
    )


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """Remove a scraping source and all its associated law updates (cascade)."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with ID {source_id} not found.",
        )
    name = source.name
    db.delete(source)
    db.commit()
    return {"success": True, "message": f"Source '{name}' and all its law updates have been deleted."}


# ---------------------------------------------------------------------------
# Scrape Trigger
# ---------------------------------------------------------------------------

@router.post("/scrape")
def trigger_scrape(
    fallback: bool = False,
    until_date: Optional[str] = Query(
        default=None,
        description="Optional ISO date string (YYYY-MM-DD). Items with a title year before this date are skipped. Defaults to today.",
        example="2024-01-01",
    ),
    db: Session = Depends(get_db),
):
    """Manually trigger a crawl across all active sources.

    Pass ``until_date`` (e.g. ``2024-01-01``) to only collect items whose title
    year is on or after that date. Defaults to today's date.
    """
    # Parse the optional date filter, defaulting to today's date if not specified
    parsed_until: datetime.date = datetime.date.today()
    if until_date:
        try:
            parsed_until = datetime.date.fromisoformat(until_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid until_date format '{until_date}'. Expected YYYY-MM-DD.",
            )

    try:
        results = crawl_all_sources(db, fallback=fallback, until_date=parsed_until)
        flat_list = []
        for src_name, titles in results.items():
            flat_list.extend(titles)

        return {
            "success": True,
            "sourcesScraped": len(results),
            "newUpdates": flat_list,
            "until_date": until_date or None,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing scraper pipeline: {str(e)}",
        )
