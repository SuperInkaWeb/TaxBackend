import asyncio
import traceback
from datetime import datetime, timezone
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
from app.services.sire.compras import descargar_propuesta_compras
from app.services.sire.ventas import descargar_propuesta_ventas
from app.models.file_mapping import CompanyFileMapping
from app.services.parser.empresa_file import parse_empresa_file, KNOWN_FORMAT_COLUMNS_HELP
from app.services.parser.sunat_propuesta import parse_sunat_propuesta
from app.api.v1.file_mapping import _model_to_mapping
from app.services.reconciliation.engine import reconcile
from app.services.report.excel_generator import generate_excel, generate_csv_b, EXCEL_B_LIMIT
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
    return resp


async def _run_reconciliation_task(
    job_id: int,
    empresa_content: bytes,
    empresa_filename: str,
    company_id: int,
    periodo: str,
    tipo_libro: TipoLibro,
) -> None:
    """
    Tarea de fondo que ejecuta la conciliación completa.
    Abre su propia sesión de DB (la del request ya cerró).
    """
    db = SessionLocal()
    try:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        company = db.query(Company).filter(Company.id == company_id).first()
        creds = db.query(CompanyCredentials).filter(CompanyCredentials.company_id == company_id).first()

        job.status = JobStatus.procesando
        db.commit()

        saved_mapping_model = db.query(CompanyFileMapping).filter(
            CompanyFileMapping.company_id == company_id
        ).first()
        saved_mapping = _model_to_mapping(saved_mapping_model) if saved_mapping_model else None
        empresa_records, used_mapping = await asyncio.to_thread(
            parse_empresa_file, empresa_content, empresa_filename, saved_mapping
        )

        if not empresa_records:
            warnings = used_mapping.warnings
            raise ValueError(
                f"No se pudieron extraer registros del archivo. "
                f"{'Usa /file-mapping/preview para configurar el formato.' if not saved_mapping_model else ''} "
                f"Detalle: {'; '.join(warnings)}"
            )

        if not used_mapping.known_format:
            raise ValueError(
                f"El archivo no tiene el formato esperado. Debe ser un CSV con las columnas: "
                f"{KNOWN_FORMAT_COLUMNS_HELP}."
            )

        async def get_token(force_refresh: bool = False) -> str:
            return await get_sunat_token(company_id, creds, company.ruc, force_refresh)

        if tipo_libro == TipoLibro.compras:
            sunat_bytes = await descargar_propuesta_compras(get_token, periodo, company.ruc)
        else:
            sunat_bytes = await descargar_propuesta_ventas(get_token, periodo, company.ruc)

        sunat_records = await asyncio.to_thread(parse_sunat_propuesta, sunat_bytes, tipo_libro.value)

        recon_output = await asyncio.to_thread(reconcile, empresa_records, sunat_records)

        excel_bytes = await asyncio.to_thread(
            generate_excel,
            output=recon_output,
            empresa_nombre=company.nombre_razon_social,
            ruc=company.ruc,
            periodo=periodo,
            tipo_libro=tipo_libro.value,
        )

        csv_b_bytes = None
        if len(recon_output.scenario_b) > EXCEL_B_LIMIT:
            csv_b_bytes = await asyncio.to_thread(generate_csv_b, recon_output)

        filename_xlsx = f"{company.ruc}_{periodo}_{tipo_libro.value}.xlsx"
        path_xlsx = f"reportes/{company_id}/{job_id}/{filename_xlsx}"
        storage.save(path_xlsx, excel_bytes)

        path_csv = None
        if csv_b_bytes is not None:
            filename_csv = f"{company.ruc}_{periodo}_{tipo_libro.value}_B.csv"
            path_csv = f"reportes/{company_id}/{job_id}/{filename_csv}"
            storage.save(path_csv, csv_b_bytes)

        result = ReconciliationResult(
            job_id=job_id,
            escenario_a_count=len(recon_output.scenario_a),
            escenario_b_count=len(recon_output.scenario_b),
            escenario_c_count=len(recon_output.scenario_c),
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
        )
        db.add(report)

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

    background_tasks.add_task(
        _run_reconciliation_task,
        job.id,
        empresa_content,
        archivo.filename or "",
        company.id,
        periodo,
        tipo_libro,
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
