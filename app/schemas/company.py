from pydantic import BaseModel
from datetime import datetime
from app.models.company import CompanyStatus


class CompanyCreate(BaseModel):
    nombre_razon_social: str
    ruc: str


class CompanyUpdate(BaseModel):
    nombre_razon_social: str | None = None
    status: CompanyStatus | None = None


class CompanyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    nombre_razon_social: str
    ruc: str
    status: CompanyStatus
    created_at: datetime
    has_credentials: bool = False


class CredentialsCreate(BaseModel):
    usuario_sol: str
    clave_sol: str
    client_id: str
    client_secret: str


class CredentialsResponse(BaseModel):
    model_config = {"from_attributes": True}

    usuario_sol: str
    client_id: str
    updated_at: datetime
