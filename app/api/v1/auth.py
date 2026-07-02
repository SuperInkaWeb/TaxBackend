from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    if user.status == UserStatus.inactivo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")
    if user.status == UserStatus.pendiente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta pendiente de aprobación")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")

    user = db.query(User).filter(User.id == int(data["sub"])).first()
    if not user or user.status != UserStatus.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
