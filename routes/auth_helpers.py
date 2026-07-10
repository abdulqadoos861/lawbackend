import os
import hashlib
import secrets
import datetime
from typing import Optional
from fastapi import Header, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import AdminSession, AdminAccount

def hash_password(password: str) -> str:
    """Hash password using PBKDF2 HMAC SHA-256 with a unique salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify stored hash against provided password."""
    try:
        salt, key_hex = hashed.split(":")
        ref_key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return secrets.compare_digest(ref_key, bytes.fromhex(key_hex))
    except Exception:
        return False

def get_current_admin(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> int:
    """Dependency to validate AdminSession token and return admin_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token."
        )
    token = authorization.split(" ")[1]
    session = db.query(AdminSession).filter(AdminSession.token == token).first()
    if not session or session.expires_at < datetime.datetime.utcnow():
        if session:
            db.delete(session)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid."
        )
    return session.admin_id
