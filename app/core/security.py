from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt, JWTError
import bcrypt
from cryptography.fernet import Fernet
from app.core.config import settings


_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode({"sub": str(subject), "exp": expire}, settings.SECRET_KEY, settings.ALGORITHM)


def create_refresh_token(subject: Any) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "refresh"},
        settings.SECRET_KEY,
        settings.ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return {}


def encrypt_field(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_field(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
