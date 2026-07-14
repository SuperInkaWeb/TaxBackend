"""
Resetea la contraseña de una cuenta local.

Uso (desde la raíz del backend):
    venv\\Scripts\\python.exe scripts\\reset_password.py

Pide el email y la contraseña nueva de forma interactiva (la contraseña
no se muestra al escribirla). También lista las cuentas existentes.
"""

import sys
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User


def main() -> None:
    db = SessionLocal()
    try:
        print("Cuentas registradas:")
        for u in db.query(User).order_by(User.id).all():
            print(f"  [{u.id}] {u.email:40} rol={u.role.value:10} estado={u.status.value}")
        print()

        email = input("Email de la cuenta a resetear: ").strip()
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"No existe una cuenta con el email {email!r}")
            sys.exit(1)

        pw1 = getpass.getpass("Contraseña nueva (no se muestra): ")
        if len(pw1) < 8:
            print("La contraseña debe tener al menos 8 caracteres.")
            sys.exit(1)
        pw2 = getpass.getpass("Repite la contraseña: ")
        if pw1 != pw2:
            print("Las contraseñas no coinciden.")
            sys.exit(1)

        user.password_hash = hash_password(pw1)
        db.commit()
        print(f"Contraseña actualizada para {user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
