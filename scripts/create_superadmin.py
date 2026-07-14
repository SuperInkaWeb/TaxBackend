"""
Script de uso único para crear el primer superadmin.
Uso: python scripts/create_superadmin.py
"""
import sys
import os
from getpass import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import PASSWORD_MIN


def main():
    email = input("Email del superadmin: ").strip()
    nombre = input("Nombre completo: ").strip()
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
