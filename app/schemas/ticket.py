from pydantic import BaseModel, Field
from datetime import datetime
from app.models.ticket import TicketStatus


class TicketCreate(BaseModel):
    asunto: str = Field(min_length=3, max_length=200)
    mensaje: str = Field(min_length=3, max_length=5000)


class TicketReply(BaseModel):
    mensaje: str = Field(min_length=1, max_length=5000)


class TicketMessageResponse(BaseModel):
    id: int
    mensaje: str
    created_at: datetime
    author_nombre: str
    author_role: str
    es_soporte: bool


class TicketResponse(BaseModel):
    id: int
    asunto: str
    status: TicketStatus
    company_id: int | None
    company_nombre: str | None
    created_by_nombre: str
    created_by_email: str
    created_at: datetime
    updated_at: datetime
    num_mensajes: int


class TicketDetailResponse(TicketResponse):
    mensajes: list[TicketMessageResponse]
