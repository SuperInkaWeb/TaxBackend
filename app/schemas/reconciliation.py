from pydantic import BaseModel, field_validator
from datetime import datetime
from app.models.reconciliation import TipoLibro, JobStatus


class ReconciliationCreate(BaseModel):
    periodo: str
    tipo_libro: TipoLibro

    @field_validator("periodo")
    @classmethod
    def validate_periodo(cls, v: str) -> str:
        if len(v) != 6 or not v.isdigit():
            raise ValueError("El periodo debe tener formato AAAAMM (ej. 202601)")
        year, month = int(v[:4]), int(v[4:])
        if not (2020 <= year <= 2099) or not (1 <= month <= 12):
            raise ValueError("Periodo inválido")
        return v


class ReconciliationResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    escenario_a_count: int
    escenario_b_count: int
    escenario_c_count: int
    igv_diferencia_total: float
    tiene_alertas_rojas: bool


class ReconciliationJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    periodo: str
    tipo_libro: TipoLibro
    status: JobStatus
    empresa_filename: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    result: ReconciliationResultResponse | None = None
    has_report: bool = False
    has_csv_b: bool = False
