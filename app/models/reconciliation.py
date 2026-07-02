import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, DateTime, ForeignKey, Integer, Text, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TipoLibro(str, enum.Enum):
    compras = "compras"
    ventas = "ventas"


class JobStatus(str, enum.Enum):
    en_cola = "en_cola"
    procesando = "procesando"
    completado = "completado"
    error = "error"


class ReconciliationJob(Base):
    __tablename__ = "reconciliation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    periodo: Mapped[str] = mapped_column(String(6), nullable=False)
    tipo_libro: Mapped[TipoLibro] = mapped_column(Enum(TipoLibro), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.en_cola, nullable=False)
    empresa_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="reconciliation_jobs")
    created_by_user: Mapped["User"] = relationship("User", back_populates="reconciliation_jobs")
    result: Mapped["ReconciliationResult | None"] = relationship("ReconciliationResult", back_populates="job", uselist=False)
    report_file: Mapped["ReportFile | None"] = relationship("ReportFile", back_populates="job", uselist=False)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("reconciliation_jobs.id"), unique=True, nullable=False)

    escenario_a_count: Mapped[int] = mapped_column(Integer, default=0)
    escenario_b_count: Mapped[int] = mapped_column(Integer, default=0)
    escenario_c_count: Mapped[int] = mapped_column(Integer, default=0)
    igv_diferencia_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tiene_alertas_rojas: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped["ReconciliationJob"] = relationship("ReconciliationJob", back_populates="result")


class ReportFile(Base):
    __tablename__ = "report_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("reconciliation_jobs.id"), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    csv_b_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    csv_b_file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job: Mapped["ReconciliationJob"] = relationship("ReconciliationJob", back_populates="report_file")
