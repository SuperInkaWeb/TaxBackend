import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.api.deps import get_current_user, require_any_role
from app.models.user import User, UserRole
from app.models.company import Company
from app.models.credentials import CompanyCredentials
from app.models.reconciliation import ReconciliationJob, ReconciliationResult, ReportFile, TipoLibro, JobStatus
from app.schemas.reconciliation import ReconciliationCreate, ReconciliationJobResponse
from app.services.sire.auth import get_sunat_token
from app.services.sire.compras import (
    solicitar_export_compras, consultar_ticket_compras, descargar_ticket_compras,
)
from app.services.sire.ventas import (
    solicitar_export_ventas, consultar_ticket_ventas, descargar_ticket_ventas,
)
from app.models.file_mapping import CompanyFileMapping
from app.services.parser.empresa_file import parse_empresa_file, KNOWN_FORMAT_COLUMNS_HELP, PLE81_FORMAT_HELP
from app.services.parser.mapeo import parse_con_columnas, validar_mapeo
from app.services.parser.sunat_propuesta import parse_sunat_propuesta
from app.services.reconciliation.engine import reconcile
from app.services.report.excel_generator import generate_excel, generate_csv_b, generate_csv_d, EXCEL_B_LIMIT, EXCEL_D_LIMIT
from app.storage import storage

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


def _get_company_and_creds(user: User, db: Session) -> tuple[Company, CompanyCredentials]:
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")
    creds = db.query(CompanyCredentials).filter(CompanyCredentials.company_id == company.id).first()
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credenciales SUNAT no configuradas. El administrador de la empresa debe configurarlas primero.",
        )
    return company, creds


def _check_job_access(job: ReconciliationJob, user: User) -> None:
    """Admins ven todo; empresa ve los de su empresa; usuario solo los suyos."""
    if user.role in (UserRole.superadmin, UserRole.admin):
        return
    if job.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")
    if user.role == UserRole.usuario and job.created_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")


def _build_response(job: ReconciliationJob) -> ReconciliationJobResponse:
    resp = ReconciliationJobResponse.model_validate(job)
    resp.has_report = job.report_file is not None
    resp.has_csv_b = (
        job.report_file is not None
        and job.report_file.csv_b_storage_path is not None
    )
    resp.has_csv_d = (
        job.report_file is not None
        and job.report_file.csv_d_storage_path is not None
    )
    resp.can_resume = (
        job.status == JobStatus.error
        and job.empresa_file_path is not None
    )
    return resp


TICKET_FRESCURA_HORAS = 24


def _descripcion_cobertura(fechas: list[str] | None) -> str | None:
    """Texto legible de la cobertura declarada, para el Excel y trazabilidad."""
    if fechas is None:
        return None
    if not fechas:
        return "Mes completo"

    def fmt(d: str) -> str:
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}"

    fs = sorted(fechas)
    if len(fs) == 1:
        return fmt(fs[0])
    try:
        from datetime import date
        ds = [date.fromisoformat(f) for f in fs]
        contiguo = all((ds[i + 1] - ds[i]).days == 1 for i in range(len(ds) - 1))
    except ValueError:
        contiguo = False
    if contiguo:
        return f"del {fmt(fs[0])} al {fmt(fs[-1])}"
    if len(fs) <= 6:
        return ", ".join(fmt(f) for f in fs)
    return f"{len(fs)} días entre el {fmt(fs[0])} y el {fmt(fs[-1])}"


def _buscar_ticket_fresco(
    db: Session,
    company_id: int,
    periodo: str,
    tipo_libro: TipoLibro,
    exclude_job_id: int | None = None,
) -> ReconciliationJob | None:
    """Último job de la empresa con ticket del mismo periodo/libro y < 24h de antigüedad."""
    limite = datetime.now(timezone.utc) - timedelta(hours=TICKET_FRESCURA_HORAS)
    query = db.query(ReconciliationJob).filter(
        ReconciliationJob.company_id == company_id,
        ReconciliationJob.periodo == periodo,
        ReconciliationJob.tipo_libro == tipo_libro,
        ReconciliationJob.num_ticket.isnot(None),
        ReconciliationJob.created_at > limite,
    )
    if exclude_job_id is not None:
        query = query.filter(ReconciliationJob.id != exclude_job_id)
    return query.order_by(ReconciliationJob.id.desc()).first()


async def _run_reconciliation_task(
    job_id: int,
    empresa_content: bytes,
    empresa_filename: str,
    company_id: int,
    periodo: str,
    tipo_libro: TipoLibro,
    resume: bool = False,
    reuse: bool = False,
    mapeo_config: dict | None = None,
    cobertura_fechas: list[str] | None = None,
) -> None:
    """
    Tarea de fondo que ejecuta la conciliación completa.
    Abre su propia sesión de DB (la del request ya cerró).

    resume=True: intenta retomar el ticket SUNAT guardado en el job
    (si sigue vivo y es fresco) en vez de generar uno nuevo.
    reuse=True: el usuario eligió reutilizar la propuesta fresca de otro
    job del mismo periodo/libro (Terminado y < 24h).
    """
    db = SessionLocal()
    try:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        company = db.query(Company).filter(Company.id == company_id).first()
        creds = db.query(CompanyCredentials).filter(CompanyCredentials.company_id == company_id).first()

        job.status = JobStatus.procesando
        db.commit()

        config = mapeo_config
        if config is None:
            saved_model = db.query(CompanyFileMapping).filter(
                CompanyFileMapping.company_id == company_id,
                CompanyFileMapping.tipo_libro == tipo_libro.value,
            ).first()
            if saved_model and saved_model.columnas and saved_model.confirmed_by_user:
                config = {
                    "delimiter": saved_model.delimiter,
                    "encoding": saved_model.encoding,
                    "has_header": saved_model.has_header,
                    "skip_rows": saved_model.skip_rows,
                    "serie_numero_combinado": saved_model.serie_numero_combinado,
                    "columnas": saved_model.columnas,
                }

        if config is not None:
            val = await asyncio.to_thread(validar_mapeo, empresa_content, config, tipo_libro.value)
            if not val["ok"]:
                detalle = "; ".join(val["avisos"]) if val["avisos"] else f"faltan campos: {val['faltantes']}"
                raise ValueError(f"El mapeo de columnas no supera la validación: {detalle}")
            empresa_records = await asyncio.to_thread(
                parse_con_columnas, empresa_content, config, tipo_libro.value
            )
            if not empresa_records:
                raise ValueError("No se extrajo ningún registro con el mapeo de columnas configurado.")
        else:
            empresa_records, used_mapping = await asyncio.to_thread(
                parse_empresa_file, empresa_content, empresa_filename, None, tipo_libro.value
            )

            formato_esperado = (
                PLE81_FORMAT_HELP if tipo_libro == TipoLibro.compras
                else f"CSV con las columnas: {KNOWN_FORMAT_COLUMNS_HELP}"
            )

            if not empresa_records:
                detalle = "; ".join(used_mapping.warnings) or "no se extrajo ningún registro"
                raise ValueError(
                    f"No se pudo procesar el archivo. {detalle}. Formato esperado: {formato_esperado}."
                )

            if not used_mapping.known_format:
                raise ValueError(
                    f"El archivo no tiene el formato esperado para {tipo_libro.value}. "
                    f"Formato esperado: {formato_esperado}."
                )

        async def get_token(force_refresh: bool = False) -> str:
            return await get_sunat_token(company_id, creds, company.ruc, force_refresh)

        if tipo_libro == TipoLibro.compras:
            solicitar, consultar, descargar = (
                solicitar_export_compras, consultar_ticket_compras, descargar_ticket_compras,
            )
        else:
            solicitar, consultar, descargar = (
                solicitar_export_ventas, consultar_ticket_ventas, descargar_ticket_ventas,
            )

        num_ticket = None
        if resume and job.num_ticket:
            created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)
            es_fresco = datetime.now(timezone.utc) - created < timedelta(hours=TICKET_FRESCURA_HORAS)
            if es_fresco:
                consulta = await consultar(get_token, job.num_ticket, periodo)
                if consulta is not None:
                    estado = consulta[0].lower()
                    if "error" not in estado:
                        num_ticket = job.num_ticket

        if num_ticket is None and reuse:
            candidato = _buscar_ticket_fresco(db, company_id, periodo, tipo_libro, exclude_job_id=job_id)
            if candidato is not None:
                consulta = await consultar(get_token, candidato.num_ticket, periodo)
                if consulta is not None and "terminado" in consulta[0].lower():
                    num_ticket = candidato.num_ticket
                    job.num_ticket = num_ticket
                    job.propuesta_origen_at = candidato.propuesta_origen_at or candidato.created_at
                    db.commit()

        if num_ticket is None:
            num_ticket = await solicitar(get_token, periodo)
            job.num_ticket = num_ticket
            job.propuesta_origen_at = datetime.now(timezone.utc)
            db.commit()

        sunat_bytes = await descargar(get_token, num_ticket, periodo)

        sunat_records = await asyncio.to_thread(parse_sunat_propuesta, sunat_bytes, tipo_libro.value)

        recon_output = await asyncio.to_thread(
            reconcile, empresa_records, sunat_records, tipo_libro.value,
            set(cobertura_fechas) if cobertura_fechas is not None else None,
        )

        excel_bytes = await asyncio.to_thread(
            generate_excel,
            output=recon_output,
            empresa_nombre=company.nombre_razon_social,
            ruc=company.ruc,
            periodo=periodo,
            tipo_libro=tipo_libro.value,
            propuesta_generada=job.propuesta_origen_at,
            cobertura=_descripcion_cobertura(cobertura_fechas),
        )

        csv_b_bytes = None
        if len(recon_output.scenario_b) > EXCEL_B_LIMIT:
            csv_b_bytes = await asyncio.to_thread(generate_csv_b, recon_output, tipo_libro.value)

        csv_d_bytes = None
        if len(recon_output.scenario_d) > EXCEL_D_LIMIT:
            csv_d_bytes = await asyncio.to_thread(generate_csv_d, recon_output, tipo_libro.value)

        filename_xlsx = f"{company.ruc}_{periodo}_{tipo_libro.value}.xlsx"
        path_xlsx = f"reportes/{company_id}/{job_id}/{filename_xlsx}"
        storage.save(path_xlsx, excel_bytes)

        path_csv = None
        if csv_b_bytes is not None:
            filename_csv = f"{company.ruc}_{periodo}_{tipo_libro.value}_B.csv"
            path_csv = f"reportes/{company_id}/{job_id}/{filename_csv}"
            storage.save(path_csv, csv_b_bytes)

        path_csv_d = None
        if csv_d_bytes is not None:
            filename_csv_d = f"{company.ruc}_{periodo}_{tipo_libro.value}_D.csv"
            path_csv_d = f"reportes/{company_id}/{job_id}/{filename_csv_d}"
            storage.save(path_csv_d, csv_d_bytes)

        result = ReconciliationResult(
            job_id=job_id,
            escenario_a_count=len(recon_output.scenario_a),
            escenario_b_count=len(recon_output.scenario_b),
            escenario_c_count=len(recon_output.scenario_c),
            escenario_d_count=len(recon_output.scenario_d),
            igv_diferencia_total=recon_output.igv_diferencia_total,
            tiene_alertas_rojas=recon_output.tiene_alertas_rojas,
        )
        db.add(result)

        report = ReportFile(
            job_id=job_id,
            filename=filename_xlsx,
            storage_path=path_xlsx,
            file_size_bytes=len(excel_bytes),
            csv_b_storage_path=path_csv,
            csv_b_file_size_bytes=len(csv_b_bytes) if csv_b_bytes is not None else None,
            csv_d_storage_path=path_csv_d,
            csv_d_file_size_bytes=len(csv_d_bytes) if csv_d_bytes is not None else None,
        )
        db.add(report)

        if job.empresa_file_path:
            try:
                storage.delete(job.empresa_file_path)
            except Exception:
                pass
            job.empresa_file_path = None

        job.status = JobStatus.completado
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        tb = traceback.format_exc()
        try:
            db.rollback()
            job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
            if job:
                job.status = JobStatus.error
                job.error_message = f"{exc}\n\nTraceback:\n{tb}"[:2000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/", response_model=ReconciliationJobResponse, status_code=status.HTTP_201_CREATED)
async def run_reconciliation(
    background_tasks: BackgroundTasks,
    periodo: str = Form(..., description="Periodo en formato AAAAMM, ej. 202601"),
    tipo_libro: TipoLibro = Form(...),
    archivo: UploadFile = File(..., description="Archivo TXT o CSV de la empresa"),
    reutilizar_propuesta: bool = Form(False, description="Reutilizar propuesta SUNAT fresca si existe"),
    mapeo_columnas: str | None = Form(None, description="JSON del mapeo de columnas confirmado por el usuario"),
    cobertura_fechas: str | None = Form(
        None,
        description="JSON array de fechas AAAA-MM-DD que el archivo declara cubrir (solo ventas). Array vacío = mes completo.",
    ),
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    try:
        ReconciliationCreate(periodo=periodo, tipo_libro=tipo_libro)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.errors()[0].get("msg", "Periodo inválido. Formato esperado: AAAAMM (ej. 202601)"),
        )

    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin empresa asignada")

    company, creds = _get_company_and_creds(current_user, db)

    empresa_content = await archivo.read()
    if not empresa_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío")

    cobertura: list[str] | None = None
    if cobertura_fechas is not None and tipo_libro == TipoLibro.ventas:
        try:
            cobertura = json.loads(cobertura_fechas)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cobertura_fechas no es un JSON válido",
            )
        if not isinstance(cobertura, list) or not all(
            isinstance(f, str) and len(f) == 10 for f in cobertura
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cobertura_fechas debe ser una lista de fechas AAAA-MM-DD",
            )

    mapeo_config: dict | None = None
    if mapeo_columnas:
        try:
            mapeo_config = json.loads(mapeo_columnas)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mapeo_columnas no es un JSON válido",
            )
        saved = db.query(CompanyFileMapping).filter(
            CompanyFileMapping.company_id == company.id,
            CompanyFileMapping.tipo_libro == tipo_libro.value,
        ).first()
        if not saved:
            saved = CompanyFileMapping(company_id=company.id, tipo_libro=tipo_libro.value)
            db.add(saved)
        saved.delimiter = mapeo_config.get("delimiter", "|")
        saved.encoding = mapeo_config.get("encoding", "latin-1")
        saved.has_header = bool(mapeo_config.get("has_header", False))
        saved.skip_rows = int(mapeo_config.get("skip_rows", 0))
        saved.columnas = mapeo_config.get("columnas") or {}
        saved.serie_numero_combinado = bool(mapeo_config.get("serie_numero_combinado", False))
        saved.confirmed_by_user = True
        db.commit()

    job = ReconciliationJob(
        company_id=company.id,
        created_by_id=current_user.id,
        periodo=periodo,
        tipo_libro=tipo_libro,
        status=JobStatus.en_cola,
        empresa_filename=archivo.filename,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    upload_path = f"uploads/{company.id}/{job.id}/{archivo.filename or 'empresa.csv'}"
    storage.save(upload_path, empresa_content)
    job.empresa_file_path = upload_path
    db.commit()

    background_tasks.add_task(
        _run_reconciliation_task,
        job.id,
        empresa_content,
        archivo.filename or "",
        company.id,
        periodo,
        tipo_libro,
        False,
        reutilizar_propuesta,
        mapeo_config,
        cobertura,
    )

    return _build_response(job)


@router.post("/{job_id}/resume", response_model=ReconciliationJobResponse)
async def resume_reconciliation(
    job_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """
    Reanuda un job fallido: si el ticket SUNAT guardado sigue vivo lo retoma
    (descarga directa si ya está Terminado); si murió, genera uno nuevo.
    """
    job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job no encontrado")

    _check_job_access(job, current_user)

    if job.status != JobStatus.error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden reanudar conciliaciones en estado de error",
        )
    if not job.empresa_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este job no es reanudable (no se conservó el archivo de la empresa)",
        )

    try:
        empresa_content = storage.read(job.empresa_file_path)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de la empresa ya no está disponible. Crea una conciliación nueva.",
        )

    job.status = JobStatus.en_cola
    job.error_message = None
    db.commit()

    background_tasks.add_task(
        _run_reconciliation_task,
        job.id,
        empresa_content,
        job.empresa_filename or "",
        job.company_id,
        job.periodo,
        job.tipo_libro,
        True,
    )

    return _build_response(job)


@router.get("/", response_model=list[ReconciliationJobResponse])
def list_jobs(
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    query = db.query(ReconciliationJob)

    if current_user.role in (UserRole.superadmin, UserRole.admin):
        pass
    else:
        query = query.filter(ReconciliationJob.company_id == current_user.company_id)

    if current_user.role == UserRole.usuario:
        query = query.filter(ReconciliationJob.created_by_id == current_user.id)

    jobs = query.order_by(ReconciliationJob.created_at.desc()).all()
    return [_build_response(job) for job in jobs]


@router.get("/propuesta-disponible")
async def propuesta_disponible(
    periodo: str,
    tipo_libro: TipoLibro,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """
    Indica si existe una propuesta SUNAT fresca (< 24h, Terminada) del mismo
    periodo/libro que puede reutilizarse en vez de solicitar una nueva.
    """
    no_disponible = {"disponible": False, "generado_a": None}

    if not current_user.company_id:
        return no_disponible

    candidato = _buscar_ticket_fresco(db, current_user.company_id, periodo, tipo_libro)
    if candidato is None:
        return no_disponible

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    creds = db.query(CompanyCredentials).filter(
        CompanyCredentials.company_id == current_user.company_id
    ).first()
    if not company or not creds:
        return no_disponible

    async def get_token(force_refresh: bool = False) -> str:
        return await get_sunat_token(current_user.company_id, creds, company.ruc, force_refresh)

    consultar = consultar_ticket_compras if tipo_libro == TipoLibro.compras else consultar_ticket_ventas
    try:
        consulta = await consultar(get_token, candidato.num_ticket, periodo)
    except Exception:
        return no_disponible

    if consulta is None or "terminado" not in consulta[0].lower():
        return no_disponible

    return {
        "disponible": True,
        "generado_a": candidato.propuesta_origen_at or candidato.created_at,
    }


@router.get("/{job_id}", response_model=ReconciliationJobResponse)
def get_job(
    job_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job no encontrado")

    _check_job_access(job, current_user)
    return _build_response(job)


@router.get("/{job_id}/download")
def download_report(
    job_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
    if not job or not job.report_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")

    _check_job_access(job, current_user)

    content = storage.read(job.report_file.storage_path)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{job.report_file.filename}"'},
    )


@router.get("/{job_id}/download-csv-b")
def download_csv_b(
    job_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Descarga el CSV completo del Escenario B (puede tener millones de filas)."""
    job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
    if not job or not job.report_file or not job.report_file.csv_b_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV Escenario B no disponible")

    _check_job_access(job, current_user)

    filename = job.report_file.csv_b_storage_path.split("/")[-1]
    content = storage.read(job.report_file.csv_b_storage_path)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/download-csv-d")
def download_csv_d(
    job_id: int,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Descarga el CSV completo del Escenario D (comprobantes que coinciden OK)."""
    job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
    if not job or not job.report_file or not job.report_file.csv_d_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV Escenario D no disponible")

    _check_job_access(job, current_user)

    filename = job.report_file.csv_d_storage_path.split("/")[-1]
    content = storage.read(job.report_file.csv_d_storage_path)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
