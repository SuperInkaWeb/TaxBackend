"""
Tests de controles de seguridad: rate limiting por ventana deslizante y
contención de rutas (Path Traversal) en el storage local.
"""
import pytest

from app.core.rate_limit import SlidingWindowLimiter


def test_limiter_bloquea_tras_max_intentos():
    lim = SlidingWindowLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert lim.blocked_for("atacante") == 0
        lim.register("atacante")
    assert lim.blocked_for("atacante") > 0


def test_limiter_reset_al_exito():
    lim = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    lim.register("user@x.com")
    lim.register("user@x.com")
    assert lim.blocked_for("user@x.com") > 0
    lim.reset("user@x.com")
    assert lim.blocked_for("user@x.com") == 0


def test_limiter_expira_con_la_ventana(monkeypatch):
    import app.core.rate_limit as rl
    reloj = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: reloj[0])

    lim = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    lim.register("k")
    lim.register("k")
    assert lim.blocked_for("k") > 0

    reloj[0] += 61
    assert lim.blocked_for("k") == 0


def test_limiter_claves_independientes():
    lim = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    lim.register("a@x.com")
    assert lim.blocked_for("a@x.com") > 0
    assert lim.blocked_for("b@x.com") == 0


def test_storage_permite_ruta_interna(tmp_path, monkeypatch):
    from app.storage import local as loc
    monkeypatch.setattr(loc.settings, "STORAGE_LOCAL_PATH", str(tmp_path))
    s = loc.LocalStorage()
    resuelta = s._ruta_segura("reportes/1/23/x.xlsx")
    assert resuelta.is_relative_to(tmp_path.resolve())


def test_storage_bloquea_path_traversal(tmp_path, monkeypatch):
    from app.storage import local as loc
    monkeypatch.setattr(loc.settings, "STORAGE_LOCAL_PATH", str(tmp_path))
    s = loc.LocalStorage()
    for ruta_maliciosa in ["../fuera", "reportes/../../etc/passwd", "/etc/passwd"]:
        with pytest.raises(ValueError):
            s._ruta_segura(ruta_maliciosa)
