import os
from contextlib import contextmanager
from pathlib import Path
from app.storage.base import BaseStorage
from app.core.config import settings


def _soltar_cache(fd: int, flush: bool = False) -> None:
    """
    Le pide al kernel que suelte del page cache las páginas de este archivo
    (POSIX_FADV_DONTNEED). Sin esto, Linux mantiene los reportes grandes (Excel,
    CSV de millones de filas) cacheados en la RAM libre del contenedor, lo que
    infla la memoria medida (y facturada) aunque el proceso esté liviano.

    Solo Linux; en Windows/local no existe posix_fadvise y no hace nada.
    """
    if not hasattr(os, "posix_fadvise"):
        return
    try:
        if flush:
            os.fsync(fd)  # fadvise solo suelta páginas ya escritas a disco
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except OSError:
        pass


class LocalStorage(BaseStorage):
    def __init__(self):
        self.base_path = Path(settings.STORAGE_LOCAL_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, path: str, content: bytes) -> str:
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(content)
            f.flush()
            _soltar_cache(f.fileno(), flush=True)
        return str(path)

    @contextmanager
    def open_write(self, path: str):
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(full_path, "wb")
        try:
            yield f
        finally:
            f.flush()
            _soltar_cache(f.fileno(), flush=True)
            f.close()

    def size(self, storage_path: str) -> int:
        return (self.base_path / storage_path).stat().st_size

    def get_url(self, storage_path: str) -> str:
        return f"/api/v1/reconciliation/files/{storage_path}"

    def read(self, storage_path: str) -> bytes:
        with open(self.base_path / storage_path, "rb") as f:
            data = f.read()
            _soltar_cache(f.fileno())
        return data

    def delete(self, storage_path: str) -> None:
        full_path = self.base_path / storage_path
        if full_path.exists():
            full_path.unlink()

    def exists(self, storage_path: str) -> bool:
        return (self.base_path / storage_path).exists()
