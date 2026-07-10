import datetime
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db.database import get_db
from db.models import AdminAccount, AdminSession
from .auth_helpers import verify_password, get_current_admin

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

    return {
        "token": token,
        "username": account.username,
        "role": account.role,
        "expires_at": expires_at.isoformat()
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
