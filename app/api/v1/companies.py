from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import encrypt_field
from app.api.deps import get_current_user, require_admin_or_above, require_empresa_or_above
from app.models.user import User, UserRole
from app.models.company import Company
from app.models.credentials import CompanyCredentials
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse, CredentialsCreate, CredentialsResponse

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/", response_model=list[CompanyResponse])
def list_companies(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    companies = db.query(Company).all()
    result = []
    for c in companies:
        resp = CompanyResponse.model_validate(c)
        resp.has_credentials = c.credentials is not None
        result.append(resp)
    return result


@router.get("/me", response_model=CompanyResponse)
def get_my_company(
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin empresa asignada")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    resp = CompanyResponse.model_validate(company)
    resp.has_credentials = company.credentials is not None
    return resp


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    if db.query(Company).filter(Company.ruc == payload.ruc).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUC ya registrado")
    company = Company(**payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.put("/me/credentials", response_model=CredentialsResponse)
def upsert_my_credentials(
    payload: CredentialsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in (UserRole.empresa, UserRole.superadmin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")

    creds = db.query(CompanyCredentials).filter(
        CompanyCredentials.company_id == current_user.company_id
    ).first()

    if creds:
        creds.usuario_sol = payload.usuario_sol
        creds.clave_sol_enc = encrypt_field(payload.clave_sol)
        creds.client_id = payload.client_id
        creds.client_secret_enc = encrypt_field(payload.client_secret)
        creds.updated_by_id = current_user.id
    else:
        creds = CompanyCredentials(
            company_id=current_user.company_id,
            usuario_sol=payload.usuario_sol,
            clave_sol_enc=encrypt_field(payload.clave_sol),
            client_id=payload.client_id,
            client_secret_enc=encrypt_field(payload.client_secret),
            updated_by_id=current_user.id,
        )
        db.add(creds)

    db.commit()
    db.refresh(creds)
    return CredentialsResponse.model_validate(creds)


@router.get("/me/credentials", response_model=CredentialsResponse)
def get_my_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin empresa asignada")
    creds = db.query(CompanyCredentials).filter(
        CompanyCredentials.company_id == current_user.company_id
    ).first()
    if not creds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credenciales no configuradas")
    return CredentialsResponse.model_validate(creds)
