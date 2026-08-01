import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.mem import rss_mb
from app.api.v1.router import router
from app.api.deps import require_superadmin


def _recover_stale_jobs() -> None:
    """
    Los jobs corren como BackgroundTasks en el mismo proceso: si el servidor se
    reinicia a mitad de uno, queda huérfano en 'procesando'/'en_cola' y el
    frontend haría polling infinito. Al arrancar los marcamos como error.
    """
    from app.core.database import SessionLocal
    from app.models.reconciliation import ReconciliationJob, JobStatus

    db = SessionLocal()
    try:
        stale = db.query(ReconciliationJob).filter(
            ReconciliationJob.status.in_([JobStatus.en_cola, JobStatus.procesando])
        ).all()
        for job in stale:
            job.status = JobStatus.error
            job.error_message = (
                "El proceso fue interrumpido por un reinicio del servidor. "
                "Vuelve a ejecutar la conciliación."
            )
        if stale:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _recover_stale_jobs()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get("/health/memory", dependencies=[Depends(require_superadmin)])
def health_memory():
    """RSS del proceso (solo superadmin) para diagnosticar memoria en producción."""
    return {"rss_mb": rss_mb(), "pid": os.getpid()}
