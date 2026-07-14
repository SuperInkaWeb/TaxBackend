from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.access_request import AccessRequestStatus


class AccessRequestCreate(BaseModel):
    email: EmailStr
    nombre: str
    empresa_nombre: str
    ruc: str
    telefono: str | None = None
    mensaje: str | None = None


class AccessRequestReview(BaseModel):
    status: AccessRequestStatus
    rejection_reason: str | None = None


class AccessRequestResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    nombre: str
    empresa_nombre: str
    ruc: str
    telefono: str | None
    mensaje: str | None
    status: AccessRequestStatus
    rejection_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None
    temp_password: str | None = None
