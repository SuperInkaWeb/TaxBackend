from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, Boolean, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CompanyFileMapping(Base):
    """
    Guarda el mapeo de columnas detectado para el archivo TXT/CSV de cada empresa.
    Una vez configurado, el parser lo usa directamente sin re-detectar.
    Puede ser sobrescrito manualmente desde el frontend.
    """
    __tablename__ = "company_file_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    tipo_libro: Mapped[str] = mapped_column(String(10), default="ventas", nullable=False)

    delimiter: Mapped[str] = mapped_column(String(5), default="|")
    encoding: Mapped[str] = mapped_column(String(20), default="latin-1")
    has_header: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_rows: Mapped[int] = mapped_column(Integer, default=0)

    columnas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    serie_numero_combinado: Mapped[bool] = mapped_column(Boolean, default=False)

    col_tipo_cdp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_serie: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_importe_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rows: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company")
