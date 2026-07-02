import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AccessRequestStatus(str, enum.Enum):
    pendiente = "pendiente"
    aprobado = "aprobado"
    rechazado = "rechazado"


class AccessRequest(Base):
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    empresa_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ruc: Mapped[str] = mapped_column(String(11), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AccessRequestStatus] = mapped_column(
        Enum(AccessRequestStatus), default=AccessRequestStatus.pendiente, nullable=False
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])
