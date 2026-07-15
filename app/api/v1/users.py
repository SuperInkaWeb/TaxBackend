import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.api.deps import get_current_user, require_superadmin, require_empresa_or_above
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserChangePassword

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/password")
def change_my_password(
    payload: UserChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if settings.auth0_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña se gestiona en Auth0 (usa '¿Olvidaste tu contraseña?' en el login).",
        )
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"detail": "Contraseña actualizada"}


@router.get("/", response_model=list[UserResponse])
def list_users(
    company_id: int | None = None,
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    query = db.query(User)

    if current_user.role == UserRole.empresa:
        return (
            query
            .filter(User.company_id == current_user.company_id)
            .filter(User.role.in_([UserRole.usuario, UserRole.empresa]))
            .filter(User.id != current_user.id)
            .all()
        )

    if current_user.role == UserRole.superadmin:
        if company_id:
            return query.filter(User.company_id == company_id).all()
        return query.filter(User.role.in_([UserRole.admin, UserRole.empresa])).all()

    if company_id:
        query = query.filter(User.company_id == company_id)
    return query.filter(User.role.in_([UserRole.empresa, UserRole.usuario])).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Los administradores no pueden crear usuarios")

    if current_user.role == UserRole.empresa:
        if payload.role != UserRole.usuario:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puede crear usuarios de tipo 'usuario'")
        payload_dict = payload.model_dump()
        payload_dict["company_id"] = current_user.company_id

    elif current_user.role == UserRole.superadmin:
        if payload.role not in (UserRole.admin, UserRole.empresa):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El superadmin solo puede crear usuarios de tipo 'admin' o 'empresa'")
        payload_dict = payload.model_dump()
        if payload.role == UserRole.admin:
            payload_dict["company_id"] = None

    else:
        payload_dict = payload.model_dump()

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado")

    auth0_sub = None
    if settings.auth0_enabled:
        from app.core.auth0 import crear_usuario, enviar_reset_password, Auth0Error

        password = secrets.token_urlsafe(12) + "A1!"
        try:
            auth0_sub = crear_usuario(payload_dict["email"], payload_dict["nombre"], password)
            enviar_reset_password(payload_dict["email"])
        except Auth0Error as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    else:
        if not payload_dict.get("password"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña es obligatoria",
            )
        password = payload_dict["password"]

    user = User(
        email=payload_dict["email"],
        nombre=payload_dict["nombre"],
        password_hash=hash_password(password),
        auth0_sub=auth0_sub,
        role=payload_dict["role"],
        company_id=payload_dict.get("company_id"),
        status=UserStatus.activo,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if current_user.role == UserRole.empresa and user.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Elimina un usuario de la BD y de Auth0 (si está vinculado).
    Si el usuario tiene conciliaciones, se bloquea: desactivarlo preserva el historial.
    """
    from app.models.access_request import AccessRequest
    from app.models.company import Company
    from app.models.credentials import CompanyCredentials
    from app.models.reconciliation import ReconciliationJob
    from app.models.ticket import Ticket, TicketMessage

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propia cuenta")
    if user.role == UserRole.superadmin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede eliminar un superadmin")

    jobs = db.query(ReconciliationJob).filter(ReconciliationJob.created_by_id == user.id).count()
    if jobs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El usuario tiene {jobs} conciliación(es) en el historial. Desactívalo en su lugar.",
        )
    tickets = db.query(Ticket).filter(Ticket.created_by_id == user.id).count()
    if tickets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El usuario tiene {tickets} ticket(s) de soporte. Desactívalo en su lugar.",
        )

    if settings.auth0_enabled and user.auth0_sub:
        from app.core.auth0 import eliminar_usuario, Auth0Error

        try:
            eliminar_usuario(user.auth0_sub)
        except Auth0Error as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    db.query(AccessRequest).filter(AccessRequest.reviewed_by_id == user.id).update({"reviewed_by_id": None})
    db.query(Company).filter(Company.approved_by_id == user.id).update({"approved_by_id": None})
    db.query(CompanyCredentials).filter(CompanyCredentials.updated_by_id == user.id).update({"updated_by_id": None})
    db.query(TicketMessage).filter(TicketMessage.author_id == user.id).update({"author_id": None})

    db.delete(user)
    db.commit()
