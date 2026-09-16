from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import ActivityLog, User, UserRole
from app.schemas import TokenOut, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    first_user = db.query(User).count() == 0
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.ADMIN if first_user else UserRole.OFFICER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(ActivityLog(user_id=user.id, action="signup", entity_type="user", entity_id=user.id))
    db.commit()
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token(subject=user.email, role=user.role.value)
    db.add(ActivityLog(user_id=user.id, action="login", entity_type="user", entity_id=user.id))
    db.commit()
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user)):
    # Stateless JWT: the client discards the token.
    return None


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
