import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import router
from app.api.deps import require_superadmin


def _rss_mb() -> float | None:
    """RSS actual del proceso en MB (Linux vía /proc; Windows vía WinAPI)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)  # KB → MB
    except OSError:
        pass
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        p = ctypes.WinDLL("psapi", use_last_error=True)
        k.GetCurrentProcess.restype = wt.HANDLE
        p.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
        pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
        p.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.WorkingSetSize / 1024 / 1024, 1)
    except Exception:
        return None


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
    return {"rss_mb": _rss_mb(), "pid": os.getpid()}
