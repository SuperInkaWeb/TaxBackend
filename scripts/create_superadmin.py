"""
Script de uso único para crear el primer superadmin.
Uso: python scripts/create_superadmin.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus


def main():
    email = input("Email del superadmin: ").strip()
    nombre = input("Nombre completo: ").strip()
    password = input("Contraseña: ").strip()

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
