"""
Limitador de intentos por ventana deslizante, en memoria.

Pensado para el login: bloquea tras N intentos fallidos dentro de la ventana.
Vive en memoria de proceso — válido porque la app corre con un solo worker
(misma restricción documentada que el caché del token SUNAT).
"""

import time
from collections import defaultdict


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str, now: float) -> None:
        limite = now - self.window
        vivos = [t for t in self._attempts[key] if t > limite]
        if vivos:
            self._attempts[key] = vivos
        else:
            self._attempts.pop(key, None)

    def blocked_for(self, key: str) -> int:
        """Segundos que faltan para poder reintentar; 0 si está permitido."""
        now = time.monotonic()
        self._prune(key, now)
        intentos = self._attempts.get(key, [])
        if len(intentos) < self.max_attempts:
            return 0
        return max(1, int(intentos[0] + self.window - now))

    def register_failure(self, key: str) -> None:
        self._attempts[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)
