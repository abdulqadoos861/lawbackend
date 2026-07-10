import datetime
import secrets
import threading
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db.database import get_db, SessionLocal
from db.models import AdminAccount, AdminSession, Source
from .auth_helpers import verify_password, get_current_admin

logger = logging.getLogger(__name__)

def _run_crawl_in_background():
    """Run the daily crawl in a background thread so login is not blocked."""
    db = SessionLocal()
    try:
        from scraper.crawler import crawl_all_sources
        today = datetime.date.today()
        logger.info("First-login-of-day crawl triggered in background.")
        crawl_all_sources(db, fallback=False, until_date=today)
        logger.info("First-login-of-day crawl completed.")
    except Exception as e:
        logger.error(f"First-login-of-day crawl error: {e}")
    finally:
        db.close()

def _trigger_crawl_if_needed(db: Session):
    """Check if any source was crawled today. If not, trigger a crawl in a background thread."""
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    already_crawled_today = db.query(Source).filter(
        Source.last_crawled >= today_start
    ).first()
    if not already_crawled_today:
        thread = threading.Thread(target=_run_crawl_in_background, daemon=True)
        thread.start()
        logger.info("Background crawl thread started for first login of the day.")
        return True
    return False

router = APIRouter()

class LoginSchema(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(payload: LoginSchema, db: Session = Depends(get_db)):
    account = db.query(AdminAccount).filter(AdminAccount.username == payload.username.strip()).first()
    if not account or not verify_password(payload.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password."
        )

    # Clean old expired sessions
    db.query(AdminSession).filter(AdminSession.expires_at < datetime.datetime.utcnow()).delete()

    # Create new session valid for 24 hours
    token = secrets.token_hex(32)
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    
    session = AdminSession(
        token=token,
        admin_id=account.id,
        expires_at=expires_at
    )
    db.add(session)
    db.commit()

    # Trigger crawl in background if no crawl has run today
    crawl_triggered = _trigger_crawl_if_needed(db)

    return {
        "token": token,
        "username": account.username,
        "role": account.role,
        "expires_at": expires_at.isoformat(),
        "crawl_triggered": crawl_triggered
    }

@router.post("/logout")
def logout(authorization: str = Header(...), db: Session = Depends(get_db)):
    if authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        db.query(AdminSession).filter(AdminSession.token == token).delete()
        db.commit()
    return {"success": True, "message": "Successfully logged out."}

@router.get("/verify")
def verify(admin_id: int = Depends(get_current_admin), db: Session = Depends(get_db)):
    account = db.query(AdminAccount).filter(AdminAccount.id == admin_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin account not found."
        )
    return {
        "success": True,
        "admin_id": admin_id,
        "username": account.username,
        "role": account.role
    }


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
def change_password(
    payload: ChangePasswordSchema,
    db: Session = Depends(get_db),
    admin_id: int = Depends(get_current_admin)
):
    account = db.query(AdminAccount).filter(AdminAccount.id == admin_id).first()
    if not account or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password."
        )
    
    # Validation checks
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long."
        )

    from .auth_helpers import hash_password
    account.password_hash = hash_password(payload.new_password.strip())
    
    # Revoke sessions for this admin account for security
    db.query(AdminSession).filter(AdminSession.admin_id == admin_id).delete()
    db.commit()
    
    return {"success": True, "message": "Password changed successfully. Please log in again."}
