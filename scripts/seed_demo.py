"""Seed demo data for HopFog-Web.

Run:
  python scripts/seed_demo.py

It will:
- create roles (admin, resident) if missing
- create an admin user (admin@example.com / admin123)
- create 10 resident users (resident1@example.com / res1234 ...)

This is helpful for UI testing without hardware.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from database.connection import engine, SessionLocal
from database.models import Base, User, Role, UserRole
from routes.auth import get_password_hash


def get_or_create_role(db: Session, name: str) -> Role:
    r = db.query(Role).filter(Role.name == name).first()
    if r:
        return r
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def link_role(db: Session, user_id: int, role_id: int) -> None:
    if db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role_id).first():
        return
    db.add(UserRole(user_id=user_id, role_id=role_id))
    db.commit()


def get_or_create_user(db: Session, email: str, username: str, password: str, role: str) -> User:
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u
    u = User(
        email=email,
        username=username,
        password_hash=get_password_hash(password),
        role=role,
        is_active=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin_role = get_or_create_role(db, "admin")
        resident_role = get_or_create_role(db, "resident")

        admin = get_or_create_user(db, "admin@example.com", "Admin", "admin123", "admin")
        link_role(db, admin.id, admin_role.id)

        for i in range(1, 11):
            u = get_or_create_user(db, f"resident{i}@example.com", f"Resident {i}", "res1234", "mobile")
            link_role(db, u.id, resident_role.id)

        print("Seed complete.")
        print("Admin: admin@example.com / admin123")
        print("Residents: resident1@example.com ... resident10@example.com / res1234")
    finally:
        db.close()


if __name__ == "__main__":
    main()
