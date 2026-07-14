"""
Tests de los controles de seguridad del login: rate limiting por ventana
deslizante y política de contraseñas mínima.
"""
import pytest
from pydantic import ValidationError

from app.core.rate_limit import SlidingWindowLimiter
from app.schemas.user import UserCreate, UserChangePassword


def test_limiter_bloquea_tras_max_intentos():
    lim = SlidingWindowLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert lim.blocked_for("atacante") == 0
        lim.register_failure("atacante")
    assert lim.blocked_for("atacante") > 0


def test_limiter_reset_al_exito():
    lim = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    lim.register_failure("user@x.com")
    lim.register_failure("user@x.com")
    assert lim.blocked_for("user@x.com") > 0
    lim.reset("user@x.com")
    assert lim.blocked_for("user@x.com") == 0


def test_limiter_expira_con_la_ventana(monkeypatch):
    import app.core.rate_limit as rl
    reloj = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: reloj[0])

    lim = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    lim.register_failure("k")
    lim.register_failure("k")
    assert lim.blocked_for("k") > 0

    reloj[0] += 61
    assert lim.blocked_for("k") == 0


def test_limiter_claves_independientes():
    lim = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    lim.register_failure("a@x.com")
    assert lim.blocked_for("a@x.com") > 0
    assert lim.blocked_for("b@x.com") == 0


def test_password_corta_rechazada_en_creacion():
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.com", nombre="A", password="1234567", role="usuario")


def test_password_valida_aceptada():
    u = UserCreate(email="a@b.com", nombre="A", password="12345678", role="usuario")
    assert u.password == "12345678"


def test_password_corta_rechazada_en_cambio():
    with pytest.raises(ValidationError):
        UserChangePassword(current_password="x", new_password="corta")
