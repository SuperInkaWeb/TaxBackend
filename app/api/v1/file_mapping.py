"""
Endpoints del mapeo de columnas (sistema v2, por libro).

- /analizar : inspecciona un archivo → columnas + mapeo propuesto + validación.
  Lo usan tanto la tarjeta de la conciliación como el apartado "Formato de archivo".
- /validar  : re-valida un mapeo ajustado (aritmética + obligatorios).
- /guardar  : guarda DELIBERADAMENTE el formato de la empresa (por libro).
- /guardado : consulta / elimina el formato guardado.

El guardado ya no es automático: una conciliación usa el formato guardado si
existe, pero solo el apartado (o el checkbox explícito) lo persiste.
"""

import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import require_any_role, require_empresa_or_above
from app.models.user import User
from app.models.file_mapping import CompanyFileMapping
from app.services.parser.mapeo import analizar_archivo, validar_mapeo

router = APIRouter(prefix="/file-mapping", tags=["file-mapping"])

_LIBROS = ("ventas", "compras")


def _validar_libro(tipo_libro: str) -> None:
    if tipo_libro not in _LIBROS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tipo_libro inválido")


def _mapping_to_config(m: CompanyFileMapping) -> dict:
    return {
        "delimiter": m.delimiter,
        "encoding": m.encoding,
        "has_header": m.has_header,
        "skip_rows": m.skip_rows,
        "serie_numero_combinado": m.serie_numero_combinado,
        "columnas": m.columnas or {},
    }


def _saved_response(m: CompanyFileMapping | None) -> dict | None:
    if not m or not m.columnas or not m.confirmed_by_user:
        return None
    return {
        "tipo_libro": m.tipo_libro,
        **_mapping_to_config(m),
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


@router.post("/analizar")
async def analizar(
    tipo_libro: str = Form(...),
    archivo: UploadFile = File(...),
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Analiza un archivo: columnas con muestras + mapeo propuesto + validación."""
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")
    _validar_libro(tipo_libro)

    content = await archivo.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío")

    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id,
        CompanyFileMapping.tipo_libro == tipo_libro,
    ).first()
    saved_config = _mapping_to_config(saved) if (saved and saved.columnas and saved.confirmed_by_user) else None

    resultado = analizar_archivo(content, tipo_libro, saved_config)
    if "error" in resultado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resultado["error"])
    resultado["tiene_guardado"] = saved_config is not None
    return resultado


@router.post("/validar")
async def validar(
    tipo_libro: str = Form(...),
    config: str = Form(..., description="JSON del mapeo a validar"),
    archivo: UploadFile = File(...),
    current_user: User = Depends(require_any_role),
):
    """Re-valida un mapeo ajustado contra el archivo (aritmética + obligatorios)."""
    _validar_libro(tipo_libro)
    try:
        cfg = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config no es JSON válido")
    content = await archivo.read()
    return validar_mapeo(content, cfg, tipo_libro)


def _guardar_config(db: Session, company_id: int, tipo_libro: str, cfg: dict) -> CompanyFileMapping:
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == company_id,
        CompanyFileMapping.tipo_libro == tipo_libro,
    ).first()
    if not saved:
        saved = CompanyFileMapping(company_id=company_id, tipo_libro=tipo_libro)
        db.add(saved)
    saved.delimiter = cfg.get("delimiter", "|")
    saved.encoding = cfg.get("encoding", "latin-1")
    saved.has_header = bool(cfg.get("has_header", False))
    saved.skip_rows = int(cfg.get("skip_rows", 0))
    saved.columnas = cfg.get("columnas") or {}
    saved.serie_numero_combinado = bool(cfg.get("serie_numero_combinado", False))
    saved.confirmed_by_user = True
    saved.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(saved)
    return saved


@router.post("/guardar")
async def guardar(
    tipo_libro: str = Form(...),
    config: str = Form(...),
    archivo: UploadFile = File(...),
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """
    Guarda deliberadamente el formato de la empresa para un libro.
    Valida la aritmética contra la muestra antes de persistir.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")
    _validar_libro(tipo_libro)
    try:
        cfg = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config no es JSON válido")

    content = await archivo.read()
    val = validar_mapeo(content, cfg, tipo_libro)
    if not val["ok"]:
        detalle = "; ".join(val["avisos"]) if val["avisos"] else f"faltan campos: {val['faltantes']}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El mapeo no supera la validación: {detalle}",
        )

    saved = _guardar_config(db, current_user.company_id, tipo_libro, cfg)
    return _saved_response(saved)


@router.get("/guardado")
def get_guardado(
    tipo_libro: str,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Devuelve el formato guardado de la empresa para un libro, o null."""
    _validar_libro(tipo_libro)
    if not current_user.company_id:
        return None
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id,
        CompanyFileMapping.tipo_libro == tipo_libro,
    ).first()
    return _saved_response(saved)


@router.delete("/guardado", status_code=status.HTTP_204_NO_CONTENT)
def delete_guardado(
    tipo_libro: str,
    current_user: User = Depends(require_empresa_or_above),
    db: Session = Depends(get_db),
):
    """Elimina el formato guardado de la empresa para un libro."""
    _validar_libro(tipo_libro)
    if not current_user.company_id:
        return
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == current_user.company_id,
        CompanyFileMapping.tipo_libro == tipo_libro,
    ).first()
    if saved:
        db.delete(saved)
        db.commit()
