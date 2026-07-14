"""
Crea en Auth0 los usuarios locales que aún no están vinculados (auth0_sub vacío)
y les envía el email para establecer su contraseña.

Uso:
    venv\\Scripts\\python.exe scripts\\migrar_usuarios_auth0.py           # solo los no vinculados
    venv\\Scripts\\python.exe scripts\\migrar_usuarios_auth0.py --relink  # re-vincula TODOS
                                                                          # (cambio de tenant)

--relink: úsalo al pasar del tenant personal al corporativo — crea cada usuario
en el tenant nuevo y sobreescribe su auth0_sub.

Requiere AUTH0_* configurados en .env.
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User, UserStatus


def main() -> None:
    if not settings.auth0_enabled:
        print("AUTH0_DOMAIN / AUTH0_AUDIENCE no están configurados en .env")
        sys.exit(1)

    from app.core.auth0 import crear_usuario, enviar_reset_password, Auth0Error

    relink = "--relink" in sys.argv

    db = SessionLocal()
    try:
        query = db.query(User).filter(User.status == UserStatus.activo)
        if not relink:
            query = query.filter(User.auth0_sub.is_(None))
        usuarios = query.order_by(User.id).all()

        if not usuarios:
            print("No hay usuarios pendientes de vincular.")
            return

        print(f"Tenant destino: {settings.AUTH0_DOMAIN}")
        print(f"Usuarios a {'re-vincular' if relink else 'vincular'}: {len(usuarios)}")
        for u in usuarios:
            print(f"  {u.email} ({u.role.value})")
        if input("¿Continuar? (si/no): ").strip().lower() not in ("si", "sí", "s", "y", "yes"):
            print("Cancelado.")
            return

        for u in usuarios:
            try:
                password_inicial = secrets.token_urlsafe(12) + "A1!"
                sub = crear_usuario(u.email, u.nombre, password_inicial)
                u.auth0_sub = sub
                db.commit()
                enviar_reset_password(u.email)
                print(f"  OK  {u.email} -> {sub} (email de contraseña enviado)")
            except Auth0Error as e:
                db.rollback()
                print(f"  ERROR  {u.email}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
