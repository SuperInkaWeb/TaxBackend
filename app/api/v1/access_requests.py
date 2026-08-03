import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
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

    if payload.status == AccessRequestStatus.aprobado:
        if db.query(Company).filter(Company.ruc == req.ruc).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUC ya registrado en el sistema")

        company = Company(nombre_razon_social=req.empresa_nombre, ruc=req.ruc, approved_by_id=current_user.id)
        db.add(company)
        db.flush()

        from app.core.auth0 import crear_usuario, enviar_reset_password, Auth0Error

        # Usuario creado en Auth0 (identidad y contraseña las gestiona Auth0, que
        # envía el email para establecerla); el registro local guarda el vínculo.
        try:
            auth0_sub = crear_usuario(req.email, req.nombre, secrets.token_urlsafe(12) + "A1!")
            enviar_reset_password(req.email)
        except Auth0Error as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

        user = User(
            email=req.email,
            nombre=req.nombre,
            auth0_sub=auth0_sub,
            role=UserRole.empresa,
            company_id=company.id,
            status=UserStatus.activo,
        )
        db.add(user)

    db.commit()
    db.refresh(req)
    return AccessRequestResponse.model_validate(req)
