from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from app.models.user import UserRole, UserStatus

PASSWORD_MIN = 8


class UserCreate(BaseModel):
    email: EmailStr
    nombre: str
    password: str | None = Field(default=None, min_length=PASSWORD_MIN)
    role: UserRole
    company_id: int | None = None


class UserUpdate(BaseModel):
    nombre: str | None = None
    email: EmailStr | None = None
    status: UserStatus | None = None


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    nombre: str
    role: UserRole
    status: UserStatus
    company_id: int | None
    created_at: datetime


class UserChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=PASSWORD_MIN)
