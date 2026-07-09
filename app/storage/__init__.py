from app.core.config import settings
from app.storage.base import BaseStorage


def get_storage() -> BaseStorage:
    if settings.STORAGE_BACKEND == "local":
        from app.storage.local import LocalStorage
        return LocalStorage()
    elif settings.STORAGE_BACKEND == "r2":
        from app.storage.r2 import R2Storage
        return R2Storage()
    raise ValueError(f"STORAGE_BACKEND desconocido: {settings.STORAGE_BACKEND}")


storage = get_storage()
