from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])

_limite_por_email = SlidingWindowLimiter(max_attempts=5, window_seconds=900)
_limite_por_ip = SlidingWindowLimiter(max_attempts=20, window_seconds=900)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email_key = payload.email.strip().lower()
    ip = request.client.host if request.client else "desconocida"

    espera = max(_limite_por_email.blocked_for(email_key), _limite_por_ip.blocked_for(ip))
    if espera:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {espera // 60 + 1} minuto(s).",
        )

    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        _limite_por_email.register_failure(email_key)
        _limite_por_ip.register_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    if user.status == UserStatus.inactivo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")
    if user.status == UserStatus.pendiente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta pendiente de aprobación")

    _limite_por_email.reset(email_key)

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
