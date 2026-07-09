from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def save(self, path: str, content: bytes) -> str:
        """Guarda el archivo y devuelve el storage_path."""

    @abstractmethod
    def get_url(self, storage_path: str) -> str:
        """Devuelve una URL de descarga para el archivo."""

    @abstractmethod
    def read(self, storage_path: str) -> bytes:
        """Lee y devuelve el contenido del archivo."""

    @abstractmethod
    def delete(self, storage_path: str) -> None:
        """Elimina el archivo si existe."""
