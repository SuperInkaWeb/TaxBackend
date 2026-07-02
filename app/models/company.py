import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CompanyStatus(str, enum.Enum):
    activo = "activo"
    inactivo = "inactivo"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre_razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    ruc: Mapped[str] = mapped_column(String(11), unique=True, index=True, nullable=False)
    status: Mapped[CompanyStatus] = mapped_column(Enum(CompanyStatus), default=CompanyStatus.activo)
    approved_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", use_alter=True, name="fk_companies_approved_by"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="company", foreign_keys="User.company_id")
    credentials: Mapped["CompanyCredentials | None"] = relationship("CompanyCredentials", back_populates="company", uselist=False)
    reconciliation_jobs: Mapped[list["ReconciliationJob"]] = relationship("ReconciliationJob", back_populates="company")
