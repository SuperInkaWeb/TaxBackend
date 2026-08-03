"""
Cifrado simétrico (Fernet) para datos sensibles en reposo — hoy las credenciales
SUNAT de cada empresa (client_secret, clave SOL). La autenticación de usuarios se
delega por completo a Auth0 (ver app/core/auth0.py); no hay JWT ni contraseñas
propias en el sistema.
"""
from cryptography.fernet import Fernet
from app.core.config import settings


_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_field(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_field(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
