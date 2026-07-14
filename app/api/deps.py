from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole, UserStatus

bearer_scheme = HTTPBearer()


def _user_desde_auth0(token: str, db: Session) -> User:
    from app.core.auth0 import validar_token, Auth0Error

    try:
        claims = validar_token(token)
    except Auth0Error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    user = db.query(User).filter(User.auth0_sub == claims["sub"]).first()
    if not user or user.status != UserStatus.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no registrado en el sistema o inactivo",
        )
    return user


def _user_desde_jwt_local(token: str, db: Session) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or user.status != UserStatus.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if settings.auth0_enabled:
        return _user_desde_auth0(credentials.credentials, db)
    return _user_desde_jwt_local(credentials.credentials, db)


def require_roles(*roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos para esta acción")
        return current_user
    return checker


require_superadmin = require_roles(UserRole.superadmin)
require_admin_or_above = require_roles(UserRole.superadmin, UserRole.admin)
require_empresa_or_above = require_roles(UserRole.superadmin, UserRole.admin, UserRole.empresa)
require_any_role = require_roles(UserRole.superadmin, UserRole.admin, UserRole.empresa, UserRole.usuario)
