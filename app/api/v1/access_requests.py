import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.api.deps import require_admin_or_above
from app.models.access_request import AccessRequest, AccessRequestStatus
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus
from app.schemas.access_request import AccessRequestCreate, AccessRequestReview, AccessRequestResponse

router = APIRouter(prefix="/access-requests", tags=["access-requests"])


@router.post("/", response_model=AccessRequestResponse, status_code=status.HTTP_201_CREATED)
def create_access_request(payload: AccessRequestCreate, db: Session = Depends(get_db)):
    if db.query(AccessRequest).filter(
        AccessRequest.email == payload.email,
        AccessRequest.status == AccessRequestStatus.pendiente,
    ).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una solicitud pendiente con ese email")

    request = AccessRequest(**payload.model_dump())
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


@router.get("/", response_model=list[AccessRequestResponse])
def list_access_requests(
    status_filter: AccessRequestStatus | None = None,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    query = db.query(AccessRequest)
    if status_filter:
        query = query.filter(AccessRequest.status == status_filter)
    return query.order_by(AccessRequest.created_at.desc()).all()


@router.put("/{request_id}/review", response_model=AccessRequestResponse)
def review_access_request(
    request_id: int,
    payload: AccessRequestReview,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    req = db.query(AccessRequest).filter(AccessRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
    if req.status != AccessRequestStatus.pendiente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La solicitud ya fue revisada")

    req.status = payload.status
    req.reviewed_by_id = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)
    req.rejection_reason = payload.rejection_reason

    temp_password: str | None = None
    if payload.status == AccessRequestStatus.aprobado:
        if db.query(Company).filter(Company.ruc == req.ruc).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUC ya registrado en el sistema")

        company = Company(nombre_razon_social=req.empresa_nombre, ruc=req.ruc, approved_by_id=current_user.id)
        db.add(company)
        db.flush()

        temp_password = secrets.token_urlsafe(9)
        auth0_sub = None
        if settings.auth0_enabled:
            from app.core.auth0 import crear_usuario, enviar_reset_password, Auth0Error

            try:
                auth0_sub = crear_usuario(req.email, req.nombre, temp_password + "A1!")
                enviar_reset_password(req.email)
            except Auth0Error as e:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
            temp_password = None

        user = User(
            email=req.email,
            nombre=req.nombre,
            password_hash=hash_password(secrets.token_urlsafe(16)) if auth0_sub else hash_password(temp_password),
            auth0_sub=auth0_sub,
            role=UserRole.empresa,
            company_id=company.id,
            status=UserStatus.activo,
        )
        db.add(user)

    db.commit()
    db.refresh(req)
    resp = AccessRequestResponse.model_validate(req)
    resp.temp_password = temp_password
    return resp
