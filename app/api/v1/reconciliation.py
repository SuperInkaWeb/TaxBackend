import asyncio
import ctypes
import json
import logging
import multiprocessing
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.api.deps import require_any_role
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
from app.services.reconciliation.worker import procesar_conciliacion
from app.storage import storage

# Los subprocesos se crean con "spawn" (no "fork"): fork dentro de un servidor
# async con hilos puede provocar deadlocks; spawn arranca un intérprete limpio.
_MP_CONTEXT = multiprocessing.get_context("spawn")

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])
logger = logging.getLogger("sire.reconciliation")


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

_job_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)


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


def _resolver_mapeo_guardado(db, company_id: int, tipo_libro: TipoLibro) -> dict | None:
    """
    Devuelve el mapeo guardado de la empresa como dict plano (o None). Se
    resuelve en el proceso principal para pasarlo al subproceso, que no tiene BD.
    """
    saved = db.query(CompanyFileMapping).filter(
        CompanyFileMapping.company_id == company_id,
        CompanyFileMapping.tipo_libro == tipo_libro.value,
    ).first()
    if saved and saved.columnas and saved.confirmed_by_user:
        return {
            "delimiter": saved.delimiter,
            "encoding": saved.encoding,
            "has_header": saved.has_header,
            "skip_rows": saved.skip_rows,
            "serie_numero_combinado": saved.serie_numero_combinado,
            "columnas": saved.columnas,
        }
    return None


def _liberar_memoria() -> None:
    """
    Devuelve al sistema operativo la memoria que el asignador de Python retiene
    tras procesar millones de filas: sin esto el proceso conserva GB reservados
    aunque el job ya terminó, y el hosting los cobra igual.

    Solo aplica en Linux/glibc (el contenedor); en otros sistemas no hace nada.
    """
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


async def _run_reconciliation_task(*args, **kwargs) -> None:
    """
    Envoltorio de la conciliación: al retornar la tarea, su frame se destruye y
    con él los millones de registros; recién ahí tiene sentido pedirle al SO que
    recupere la memoria (hacerlo dentro de la tarea no liberaría nada, porque
    sus variables locales seguirían vivas).
    """
    try:
        await _ejecutar_conciliacion(*args, **kwargs)
    finally:
        _liberar_memoria()


async def _ejecutar_conciliacion(
    job_id: int,
    empresa_file_path: str,
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

    El job espera su turno en el semáforo (estado 'en_cola') antes de tocar
    RAM: así N conciliaciones simultáneas no revientan el servidor.
    """
    await _job_semaphore.acquire()
    try:
        # Fase 1: trabajo breve con la BD (leer, marcar 'procesando', pedir el
        # ticket a SUNAT). Se extraen a variables planas los datos que se usan
        # después y se cierra la sesión: durante la descarga larga (fase 2) no
        # se mantiene ninguna conexión ociosa que Neon pueda cerrar.
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
            if job is None:
                return
            company = db.query(Company).filter(Company.id == company_id).first()
            creds = db.query(CompanyCredentials).filter(CompanyCredentials.company_id == company_id).first()

            job.status = JobStatus.procesando
            db.commit()

            saved_mapping = (
                _resolver_mapeo_guardado(db, company_id, tipo_libro)
                if mapeo_config is None else None
            )

            ruc = company.ruc
            empresa_nombre = company.nombre_razon_social
            creds_snapshot = SimpleNamespace(
                client_id=creds.client_id,
                client_secret_enc=creds.client_secret_enc,
                clave_sol_enc=creds.clave_sol_enc,
                usuario_sol=creds.usuario_sol,
            )

            async def get_token(force_refresh: bool = False) -> str:
                return await get_sunat_token(company_id, creds_snapshot, ruc, force_refresh)

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

            propuesta_origen_at = job.propuesta_origen_at
            empresa_file_path_guardado = job.empresa_file_path
        finally:
            db.close()

        # Fase 2a: descarga de SUNAT (polling + ZIP, puede durar decenas de
        # minutos). Los bytes se escriben a un archivo temporal y se liberan de
        # inmediato: el servidor no retiene la propuesta en memoria.
        sunat_bytes = await descargar(get_token, num_ticket, periodo)
        fd, sunat_tmp_path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(sunat_bytes)
        finally:
            del sunat_bytes
        _liberar_memoria()

        # Fase 2b: parseo + conciliación + generación de reportes en un
        # SUBPROCESO. Todo el pico de RAM (millones de filas) vive ahí; cuando
        # el subproceso muere, el SO recupera el 100% de esa memoria — el
        # servidor se mantiene liviano y no acumula GB entre conciliaciones.
        payload = {
            "empresa_file_path": empresa_file_path,
            "empresa_filename": empresa_filename,
            "sunat_tmp_path": sunat_tmp_path,
            "tipo_libro": tipo_libro.value,
            "mapeo_config": mapeo_config,
            "saved_mapping": saved_mapping,
            "cobertura_fechas": cobertura_fechas,
            "cobertura_desc": _descripcion_cobertura(cobertura_fechas),
            "ruc": ruc,
            "empresa_nombre": empresa_nombre,
            "periodo": periodo,
            "propuesta_origen_at": propuesta_origen_at,
            "company_id": company_id,
            "job_id": job_id,
        }
        loop = asyncio.get_running_loop()
        try:
            with ProcessPoolExecutor(max_workers=1, mp_context=_MP_CONTEXT) as executor:
                resultado = await loop.run_in_executor(executor, procesar_conciliacion, payload)
        finally:
            try:
                os.remove(sunat_tmp_path)
            except OSError:
                pass

        if empresa_file_path_guardado:
            try:
                storage.delete(empresa_file_path_guardado)
            except Exception:
                pass

        # Fase 3: sesión NUEVA para guardar el resultado (conexión fresca, no
        # una que quedó ociosa durante la descarga).
        db = SessionLocal()
        try:
            db.add(ReconciliationResult(
                job_id=job_id,
                escenario_a_count=resultado["escenario_a_count"],
                escenario_b_count=resultado["escenario_b_count"],
                escenario_c_count=resultado["escenario_c_count"],
                escenario_d_count=resultado["escenario_d_count"],
                igv_diferencia_total=resultado["igv_diferencia_total"],
                tiene_alertas_rojas=resultado["tiene_alertas_rojas"],
            ))
            db.add(ReportFile(
                job_id=job_id,
                filename=resultado["filename_xlsx"],
                storage_path=resultado["path_xlsx"],
                file_size_bytes=resultado["excel_size"],
                csv_b_storage_path=resultado["path_csv"],
                csv_b_file_size_bytes=resultado["csv_b_size"],
                csv_d_storage_path=resultado["path_csv_d"],
                csv_d_file_size_bytes=resultado["csv_d_size"],
            ))
            job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
            if job:
                job.empresa_file_path = None
                job.status = JobStatus.completado
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

    except Exception as exc:
        logger.exception("Job de conciliación #%s falló", job_id)
        if isinstance(exc, (ValueError, TimeoutError)):
            mensaje = str(exc)
        else:
            mensaje = (
                "Ocurrió un error inesperado al procesar la conciliación. "
                "Vuelve a intentarlo; si persiste, contacta al soporte."
            )
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
            if job:
                job.status = JobStatus.error
                job.error_message = mensaje[:1000]
                db.commit()
        except Exception:
            pass
        finally:
            db.close()
    finally:
        _job_semaphore.release()


@router.post("/", response_model=ReconciliationJobResponse, status_code=status.HTTP_201_CREATED)
async def run_reconciliation(
    background_tasks: BackgroundTasks,
    periodo: str = Form(..., description="Periodo en formato AAAAMM, ej. 202601"),
    tipo_libro: TipoLibro = Form(...),
    archivo: UploadFile = File(..., description="Archivo TXT o CSV de la empresa"),
    reutilizar_propuesta: bool = Form(False, description="Reutilizar propuesta SUNAT fresca si existe"),
    mapeo_columnas: str | None = Form(None, description="JSON del mapeo de columnas confirmado por el usuario"),
    guardar_formato: bool = Form(False, description="Guardar el mapeo como formato de la empresa para futuras conciliaciones"),
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
        if guardar_formato and mapeo_config.get("columnas"):
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

    del empresa_content

    background_tasks.add_task(
        _run_reconciliation_task,
        job.id,
        upload_path,
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

    if not storage.exists(job.empresa_file_path):
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
        job.empresa_file_path,
        job.empresa_filename or "",
        job.company_id,
        job.periodo,
        job.tipo_libro,
        True,
    )

    return _build_response(job)


@router.get("/", response_model=list[ReconciliationJobResponse])
def list_jobs(
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    query = db.query(ReconciliationJob).options(
        joinedload(ReconciliationJob.result),
        joinedload(ReconciliationJob.report_file),
    )

    if current_user.role in (UserRole.superadmin, UserRole.admin):
        pass
    else:
        query = query.filter(ReconciliationJob.company_id == current_user.company_id)

    if current_user.role == UserRole.usuario:
        query = query.filter(ReconciliationJob.created_by_id == current_user.id)

    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    jobs = (
        query.order_by(ReconciliationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
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
