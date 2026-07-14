from app.storage.base import BaseStorage
from app.storage.local import LocalStorage


def get_storage() -> BaseStorage:
    return LocalStorage()


storage = get_storage()
