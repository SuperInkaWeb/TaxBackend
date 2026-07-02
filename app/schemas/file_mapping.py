from pydantic import BaseModel
from datetime import datetime


class FileMappingResponse(BaseModel):
    model_config = {"from_attributes": True}

    delimiter: str
    encoding: str
    has_header: bool
    skip_rows: int
    col_tipo_cdp: int | None
    col_serie: int | None
    col_numero: int | None
    col_importe_total: int | None
    confidence: float | None
    confirmed_by_user: bool
    updated_at: datetime
    sample_rows: list[list[str]] | None = None


class FileMappingManual(BaseModel):
    """El usuario corrige o confirma el mapeo desde el frontend."""
    delimiter: str = "|"
    encoding: str = "latin-1"
    has_header: bool = False
    skip_rows: int = 0
    col_tipo_cdp: int | None = None
    col_serie: int | None = None
    col_numero: int | None = None
    col_importe_total: int | None = None


class FilePreviewResponse(BaseModel):
    """Resultado del análisis previo a la conciliación."""
    detected_mapping: FileMappingResponse | None
    sample_rows: list[list[str]]
    total_rows_detected: int
    confidence: float
    warnings: list[str]
    already_confirmed: bool
