from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole, UserStatus

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or user.status != UserStatus.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    return user


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
