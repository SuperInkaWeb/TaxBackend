"""
Tickets de soporte.

- Los crean las cuentas empresa y usuario (asunto + mensaje inicial).
- Los atienden admin y superadmin: ven todos, responden y cierran.
- El creador ve los suyos (la cuenta empresa ve los de toda su empresa),
  puede responder mientras no esté cerrado y también cerrarlo.
- Estados: abierto (espera respuesta de soporte), respondido (soporte
  contestó), cerrado.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.api.deps import require_any_role
from app.models.ticket import Ticket, TicketMessage, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import (
    TicketCreate, TicketReply, TicketResponse, TicketDetailResponse, TicketMessageResponse,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

_ROLES_SOPORTE = (UserRole.superadmin, UserRole.admin)


def _es_soporte(user: User) -> bool:
    return user.role in _ROLES_SOPORTE


def _puede_ver(ticket: Ticket, user: User) -> bool:
    if _es_soporte(user):
        return True
    if user.role == UserRole.empresa:
        return ticket.company_id == user.company_id
    return ticket.created_by_id == user.id


def _to_response(t: Ticket) -> dict:
    return {
        "id": t.id,
        "asunto": t.asunto,
        "status": t.status,
        "company_id": t.company_id,
        "company_nombre": t.company.nombre_razon_social if t.company else None,
        "created_by_nombre": t.created_by.nombre,
        "created_by_email": t.created_by.email,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "num_mensajes": len(t.messages),
    }


def _mensaje_to_response(m: TicketMessage) -> TicketMessageResponse:
    return TicketMessageResponse(
        id=m.id,
        mensaje=m.mensaje,
        created_at=m.created_at,
        author_nombre=m.author.nombre if m.author else "Usuario eliminado",
        author_role=m.author.role.value if m.author else "usuario",
        es_soporte=m.author.role in _ROLES_SOPORTE if m.author else False,
    )


def _get_ticket(ticket_id: int, user: User, db: Session) -> Ticket:
    ticket = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.created_by),
            joinedload(Ticket.company),
            joinedload(Ticket.messages).joinedload(TicketMessage.author),
        )
        .filter(Ticket.id == ticket_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")
    if not _puede_ver(ticket, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos para este ticket")
    return ticket


@router.post("/", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    if _es_soporte(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los administradores atienden tickets, no los crean",
        )

    ticket = Ticket(
        asunto=payload.asunto,
        company_id=current_user.company_id,
        created_by_id=current_user.id,
        status=TicketStatus.abierto,
    )
    ticket.messages.append(TicketMessage(author_id=current_user.id, mensaje=payload.mensaje))
    db.add(ticket)
    db.commit()
    ticket = _get_ticket(ticket.id, current_user, db)
    return _to_response(ticket)


@router.get("/", response_model=list[TicketResponse])
def list_tickets(
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    query = db.query(Ticket).options(
        joinedload(Ticket.created_by),
        joinedload(Ticket.company),
        joinedload(Ticket.messages),
    )

    if current_user.role == UserRole.empresa:
        query = query.filter(Ticket.company_id == current_user.company_id)
    elif current_user.role == UserRole.usuario:
        query = query.filter(Ticket.created_by_id == current_user.id)

    tickets = query.order_by(Ticket.updated_at.desc()).all()
    return [_to_response(t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    ticket = _get_ticket(ticket_id, current_user, db)
    return {**_to_response(ticket), "mensajes": [_mensaje_to_response(m) for m in ticket.messages]}


@router.post("/{ticket_id}/messages", response_model=TicketDetailResponse)
def reply_ticket(
    ticket_id: int,
    payload: TicketReply,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    ticket = _get_ticket(ticket_id, current_user, db)
    if ticket.status == TicketStatus.cerrado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El ticket está cerrado")

    ticket.messages.append(TicketMessage(author_id=current_user.id, mensaje=payload.mensaje))
    ticket.status = TicketStatus.respondido if _es_soporte(current_user) else TicketStatus.abierto
    db.commit()

    ticket = _get_ticket(ticket_id, current_user, db)
    return {**_to_response(ticket), "mensajes": [_mensaje_to_response(m) for m in ticket.messages]}


@router.put("/{ticket_id}/cerrar", response_model=TicketResponse)
def close_ticket(
    ticket_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    ticket = _get_ticket(ticket_id, current_user, db)
    if ticket.status == TicketStatus.cerrado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El ticket ya está cerrado")
    ticket.status = TicketStatus.cerrado
    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)
