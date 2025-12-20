from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from database.deps import get_db
from database.models import User

router = APIRouter(prefix="/api/users", tags=["Users"])

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password_hash: str  # for now (later we will hash real passwords)

@router.post("")
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    # basic uniqueness checks
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=payload.password_hash,
        is_active=1
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "username": user.username}

@router.get("")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.desc()).all()
    return [{"id": u.id, "email": u.email, "username": u.username, "is_active": u.is_active} for u in users]
