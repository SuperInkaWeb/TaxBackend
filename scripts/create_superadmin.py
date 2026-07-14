"""
Script de uso único para crear el primer superadmin.
Uso: python scripts/create_superadmin.py

Modo local: pide una contraseña (oculta, con confirmación).
Modo Auth0 (AUTH0_* en .env): no pide contraseña — vincula con la cuenta
existente en Auth0 o la crea y envía el email para establecerla.
"""
import secrets
import sys
import os
from getpass import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import PASSWORD_MIN


def main():
    email = input("Email del superadmin: ").strip()
    nombre = input("Nombre completo: ").strip()

    auth0_sub = None
    if settings.auth0_enabled:
        from app.core.auth0 import crear_usuario, buscar_sub_por_email, enviar_reset_password, Auth0Error

        print(f"Modo Auth0 ({settings.AUTH0_DOMAIN}): la contraseña se gestiona en Auth0.")
        try:
            auth0_sub = buscar_sub_por_email(email)
            if auth0_sub:
                print(f"La cuenta ya existe en Auth0 ({auth0_sub}); se vincula sin enviar email.")
            else:
                auth0_sub = crear_usuario(email, nombre, secrets.token_urlsafe(12) + "A1!")
                enviar_reset_password(email)
                print("Cuenta creada en Auth0; se envió el email para establecer la contraseña.")
        except Auth0Error as e:
            print(f"ERROR de Auth0: {e}")
            return
        password = secrets.token_urlsafe(24)
    else:
        password = getpass(f"Contraseña (min {PASSWORD_MIN} caracteres, no se muestra al escribir): ").strip()
        if len(password) < PASSWORD_MIN:
            print(f"ERROR: la contraseña debe tener al menos {PASSWORD_MIN} caracteres")
            return
        if password != getpass("Confirma la contraseña: ").strip():
            print("ERROR: las contraseñas no coinciden")
            return

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"ERROR: ya existe un usuario con el email {email}")
            return

        user = User(
            email=email,
            nombre=nombre,
            password_hash=hash_password(password),
            auth0_sub=auth0_sub,
            role=UserRole.superadmin,
            status=UserStatus.activo,
        )
        db.add(user)
        db.commit()
        print(f"Superadmin creado correctamente: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
