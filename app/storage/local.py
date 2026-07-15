from pathlib import Path
from app.storage.base import BaseStorage
from app.core.config import settings


class LocalStorage(BaseStorage):
    def __init__(self):
        self.base_path = Path(settings.STORAGE_LOCAL_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, path: str, content: bytes) -> str:
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(path)

    def get_url(self, storage_path: str) -> str:
        return f"/api/v1/reconciliation/files/{storage_path}"

    def read(self, storage_path: str) -> bytes:
        return (self.base_path / storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        full_path = self.base_path / storage_path
        if full_path.exists():
            full_path.unlink()

    def exists(self, storage_path: str) -> bool:
        return (self.base_path / storage_path).exists()
