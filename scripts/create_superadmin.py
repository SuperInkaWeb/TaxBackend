"""
Script de uso único para crear el primer superadmin (autenticación 100% Auth0).
Uso: python scripts/create_superadmin.py

Vincula con la cuenta existente en Auth0 (por email) o la crea y envía el email
para establecer la contraseña. El registro local solo guarda el vínculo (auth0_sub).
"""
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User, UserRole, UserStatus


def main():
    email = input("Email del superadmin: ").strip()
    nombre = input("Nombre completo: ").strip()

    from app.core.auth0 import crear_usuario, buscar_sub_por_email, enviar_reset_password, Auth0Error

    print(f"Auth0 ({settings.AUTH0_DOMAIN}): la contraseña se gestiona en Auth0.")
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

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"ERROR: ya existe un usuario con el email {email}")
            return

        user = User(
            email=email,
            nombre=nombre,
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
