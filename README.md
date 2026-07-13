# Bot SIRE — Backend

API de conciliación tributaria SUNAT (SIRE). Compara el registro de compras/ventas
de una empresa contra la propuesta oficial del SIRE y clasifica cada comprobante en
4 escenarios (A/B/C/D), generando un reporte Excel.

## Stack

- **FastAPI** (Python 3.12+) — API REST
- **PostgreSQL** + **SQLAlchemy** + **Alembic** (migraciones)
- **pandas** — parseo de archivos de millones de filas
- **openpyxl** — generación de reportes Excel

## Requisitos del servidor

- Python 3.12+
- PostgreSQL 14+
- **7-Zip** (`p7zip-full` en Linux) — SUNAT entrega la propuesta de ventas en ZIP particionado
- ~12 GB de RAM (el parseo de la propuesta mensual completa alcanza picos altos)

## Configuración

Copia `.env.example` a `.env` y completa:

```
SECRET_KEY=...              # openssl rand -hex 32
ENCRYPTION_KEY=...          # Fernet key (ver .env.example)
DATABASE_URL=postgresql://user:pass@host:5432/sire_bot
CORS_ORIGINS=https://tu-frontend.com
```

## Puesta en marcha

```bash
python -m venv venv
venv/Scripts/activate            # Windows | source venv/bin/activate en Linux
pip install -r requirements.txt
alembic upgrade head             # crea/actualiza el esquema
uvicorn app.main:app --port 8000 # un solo worker (los jobs viven en el proceso)
```

## Tests

```bash
pytest
```

## Notas de despliegue

- **Un solo worker de uvicorn**: los jobs de conciliación y el caché del token SUNAT
  viven en memoria de proceso; múltiples workers duplicarían RAM y pelearían el token.
- **Concurrencia**: `MAX_CONCURRENT_JOBS` (config) serializa los jobs pesados. Subir
  solo si el servidor tiene RAM para varios picos simultáneos.
- Los reportes se guardan en `storage/` (disco local). En plataformas con disco
  efímero, configurar `STORAGE_BACKEND=r2` o un volumen persistente.
