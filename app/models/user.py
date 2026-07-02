import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class UserRole(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    empresa = "empresa"
    usuario = "usuario"


class UserStatus(str, enum.Enum):
    activo = "activo"
    inactivo = "inactivo"
    pendiente = "pendiente"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.activo, nullable=False)
    company_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="users", foreign_keys=[company_id])
    reconciliation_jobs: Mapped[list["ReconciliationJob"]] = relationship("ReconciliationJob", back_populates="created_by_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")
