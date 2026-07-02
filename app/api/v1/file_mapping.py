"""
Endpoints para previsualización y configuración del mapeo de columnas
del archivo TXT/CSV de la empresa.

Flujo en el frontend:
  1. Usuario sube el archivo → POST /file-mapping/preview
     Respuesta: filas en crudo + mapeo detectado + confianza
  2. Usuario revisa y opcionalmente corrige → PUT /file-mapping/confirm
     Si no necesita corregir, confirma el mapeo detectado.
  3. En conciliaciones futuras el mapeo guardado se usa automáticamente.
"""

import io
import re
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user, require_empresa_or_above
from app.models.user import User
from app.models.file_mapping import CompanyFileMapping
from app.services.parser.empresa_file import detect_mapping, ColumnMapping
from app.schemas.file_mapping import FileMappingResponse, FileMappingManual, FilePreviewResponse

router = APIRouter(prefix="/file-mapping", tags=["file-mapping"])

MAX_SAMPLE_ROWS = 5


def _model_to_mapping(model: CompanyFileMapping) -> ColumnMapping:
    m = ColumnMapping()
    m.delimiter = model.delimiter
    m.encoding = model.encoding
    m.has_header = model.has_header
    m.skip_rows = model.skip_rows
    m.col_tipo_cdp = model.col_tipo_cdp
    m.col_serie = model.col_serie
    m.col_numero = model.col_numero
    m.col_importe_total = model.col_importe_total
    m.confidence = model.detection_confidence or 0.0
    m.confirmed_by_user = model.confirmed_by_user
    return m


def _get_sample_rows(content: bytes, mapping: ColumnMapping, n: int = MAX_SAMPLE_ROWS) -> list[list[str]]:
    try:
        text = content.decode(mapping.encoding, errors="replace")
        df = pd.read_csv(
            io.StringIO(text),
            sep=re.escape(mapping.delimiter),
            header=None,
            skiprows=mapping.skip_rows,
            dtype=str,
            skip_blank_lines=True,
            on_bad_lines="skip",
            engine="python",
            nrows=n + (1 if mapping.has_header else 0),
        )
        start = 1 if mapping.has_header else 0
        rows = df.iloc[start:start + n].fillna("").values.tolist()
        return [[str(v) for v in row] for row in rows]
    except Exception:
        return []


@router.post("/preview", response_model=FilePreviewResponse)
async def preview_file(
    archivo: UploadFile = File(...),
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """
    Paso 1: Analiza el archivo sin guardar nada.
    Devuelve el mapeo detectado + filas de muestra para que el usuario pueda
    revisar y confirmar (o corregir) desde el frontend.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")

    content = await archivo.read()

    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id
    ).first()

    if saved and saved.confirmed_by_user:
        existing_mapping = _model_to_mapping(saved)
        sample = _get_sample_rows(content, existing_mapping)
        return FilePreviewResponse(
            detected_mapping=FileMappingResponse.model_validate(saved),
            sample_rows=sample,
            total_rows_detected=len(sample),
            confidence=saved.detection_confidence or 1.0,
            warnings=["Usando mapeo guardado y confirmado previamente."],
            already_confirmed=True,
        )

    detected = detect_mapping(content, archivo.filename or "")
    sample = _get_sample_rows(content, detected)

    return FilePreviewResponse(
        detected_mapping=FileMappingResponse(
            delimiter=detected.delimiter,
            encoding=detected.encoding,
            has_header=detected.has_header,
            skip_rows=detected.skip_rows,
            col_tipo_cdp=detected.col_tipo_cdp,
            col_serie=detected.col_serie,
            col_numero=detected.col_numero,
            col_importe_total=detected.col_importe_total,
            confidence=detected.confidence,
            confirmed_by_user=False,
            updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            sample_rows=None,
        ),
        sample_rows=sample,
        total_rows_detected=len(sample),
        confidence=detected.confidence,
        warnings=detected.warnings,
        already_confirmed=False,
    )


@router.put("/confirm", response_model=FileMappingResponse)
def confirm_mapping(
    payload: FileMappingManual,
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """
    Paso 2: El usuario confirma (o corrige) el mapeo detectado.
    Se guarda en DB para usarse en conciliaciones futuras.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")

    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id
    ).first()

    data = payload.model_dump()
    data["confirmed_by_user"] = True

    if saved:
        for k, v in data.items():
            setattr(saved, k, v)
    else:
        saved = CompanyFileMapping(company_id=current_user.company_id, **data)
        db.add(saved)

    db.commit()
    db.refresh(saved)
    return FileMappingResponse.model_validate(saved)


@router.get("/", response_model=FileMappingResponse | None)
def get_my_mapping(
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """Devuelve el mapeo guardado actual de la empresa, si existe."""
    if not current_user.company_id:
        return None
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id
    ).first()
    return FileMappingResponse.model_validate(saved) if saved else None


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def reset_mapping(
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """Elimina el mapeo guardado para forzar re-detección en la próxima carga."""
    if not current_user.company_id:
        return
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id
    ).first()
    if saved:
        db.delete(saved)
        db.commit()
