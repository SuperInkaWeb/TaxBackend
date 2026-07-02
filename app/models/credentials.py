from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CompanyCredentials(Base):
    """
    Credenciales SUNAT de la empresa. Campos sensibles cifrados con AES-256 (Fernet).
    La clave SOL y el client_secret nunca se almacenan en texto plano.
    """

    __tablename__ = "company_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)

    usuario_sol: Mapped[str] = mapped_column(String(50), nullable=False)
    clave_sol_enc: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(String(100), nullable=False)
    client_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="credentials")
