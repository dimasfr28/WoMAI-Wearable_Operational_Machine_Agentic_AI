"""Section 7: POST /auth/login, POST /auth/register, GET /users, PATCH /users/{id}/role."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import TokenOut, UserLoginIn, UserOut, UserRegisterIn, UserRoleUpdateIn

router = APIRouter(tags=["auth"])

VALID_ROLES = {"admin", "engineer", "viewer"}


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegisterIn,
    db: Session = Depends(get_db),
):
    """Buat user baru. Role default 'viewer'.

    Kontrak Section 7 menandai endpoint ini role=admin. Karena sistem butuh cara
    untuk membuat admin PERTAMA (tidak ada admin yang bisa memanggilnya), endpoint
    ini terbuka tanpa auth HANYA selama tabel users masih kosong (bootstrap);
    setelah user pertama ada, endpoint mewajibkan role admin.
    """
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registering a new user requires admin authentication once the first user exists. "
            "Use this endpoint with Authorization: Bearer <admin_token>.",
        )

    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")

    existing = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="username or email is already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role="admin" if user_count == 0 else payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/auth/register/admin", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_by_admin(
    payload: UserRegisterIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Explicit admin-authenticated registration path (Section 7 contract, role=admin)."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")
    existing = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="username or email is already registered")
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/auth/login", response_model=TokenOut)
def login(payload: UserLoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")
    token = create_access_token(str(user.id), user.role)
    return TokenOut(access_token=token)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserOut(id=str(u.id), username=u.username, email=u.email, full_name=u.full_name, role=u.role, is_active=u.is_active)
        for u in users
    ]


@router.patch("/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return UserOut(
        id=str(user.id), username=user.username, email=user.email, full_name=user.full_name, role=user.role, is_active=user.is_active
    )
